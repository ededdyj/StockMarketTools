import pandas as pd

from models.valuation import (
    DcfAssumptions,
    calculate_fair_value,
    calculate_scenario_valuations,
    calculate_sensitivity_table,
    reverse_dcf_implied_growth,
)


def _cashflow_with_value(value: float = 100.0):
    return pd.DataFrame({"2024-12-31": [value]}, index=["Free Cash Flow"])


def test_default_assumptions_values():
    defaults = DcfAssumptions.defaults()
    assert defaults.discount_rate == 0.10
    assert defaults.growth_rate == 0.03
    assert defaults.terminal_growth_rate == 0.02
    assert defaults.projection_years == 5


def test_modified_assumptions_change_valuation():
    cf = _cashflow_with_value()
    default_result = calculate_fair_value(cf, net_debt=0.0, shares_outstanding=1_000_000)
    aggressive = DcfAssumptions(0.08, 0.05, 0.03, 5)
    aggressive_result = calculate_fair_value(cf, net_debt=0.0, shares_outstanding=1_000_000, assumptions=aggressive)

    assert default_result is not None and aggressive_result is not None
    assert aggressive_result.enterprise_value > default_result.enterprise_value


def test_invalid_assumptions_rejected():
    invalid = DcfAssumptions(0.02, 0.03, 0.02, 5)
    valid, message = invalid.validate()
    assert not valid
    assert "Discount rate" in message


def test_calculate_fair_value_returns_explicit_equity_bridge():
    assumptions = DcfAssumptions(0.10, 0.00, 0.02, 1)
    result = calculate_fair_value(
        _cashflow_with_value(100.0),
        net_debt=20.0,
        shares_outstanding=10.0,
        assumptions=assumptions,
    )

    assert result is not None
    assert result.starting_fcf == 100.0
    assert result.projected_fcf == [100.0]
    expected_terminal = 100.0 * 1.02 / (0.10 - 0.02)
    assert round(result.terminal_value, 6) == round(expected_terminal, 6)
    assert round(result.enterprise_value, 6) == round(result.pv_explicit_fcf + result.pv_terminal_value, 6)
    assert result.equity_value == result.enterprise_value - 20.0
    assert result.fair_value_per_share == result.equity_value / 10.0


def test_scenario_dcf_outputs_bear_base_bull_values():
    scenarios = {
        "Bear": DcfAssumptions(0.12, 0.01, 0.015, 5),
        "Base": DcfAssumptions(0.10, 0.03, 0.02, 5),
        "Bull": DcfAssumptions(0.09, 0.05, 0.025, 5),
    }

    results = calculate_scenario_valuations(100.0, 0.0, 10.0, 10.0, scenarios)

    assert [result.name for result in results] == ["Bear", "Base", "Bull"]
    assert results[0].valuation.fair_value_per_share < results[1].valuation.fair_value_per_share
    assert results[2].valuation.fair_value_per_share > results[1].valuation.fair_value_per_share
    assert results[0].thesis


def test_sensitivity_table_marks_invalid_cells():
    table = calculate_sensitivity_table(
        100.0,
        0.0,
        10.0,
        DcfAssumptions(0.04, 0.02, 0.02, 5),
        discount_rate_steps=[0.0],
        terminal_growth_steps=[0.0, 0.03],
    )

    assert pd.notna(table.iloc[0][0.04])
    assert pd.isna(table.iloc[1][0.04])


def test_reverse_dcf_solves_implied_growth():
    base = DcfAssumptions(0.10, 0.04, 0.02, 5)
    valuation = calculate_fair_value(
        _cashflow_with_value(100.0),
        net_debt=0.0,
        shares_outstanding=10.0,
        assumptions=base,
    )

    reverse = reverse_dcf_implied_growth(
        valuation.fair_value_per_share,
        10.0,
        0.0,
        100.0,
        0.10,
        0.02,
        5,
    )

    assert reverse.valid
    assert round(reverse.implied_growth_rate, 3) == 0.04
    assert "market appears to require" in reverse.message
