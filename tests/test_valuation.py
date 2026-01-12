import pandas as pd

from models.valuation import DcfAssumptions, calculate_fair_value


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
