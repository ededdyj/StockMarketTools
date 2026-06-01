import pandas as pd

from data.market_inputs import MarketInputs
from models.dcf_assumptions import estimate_dynamic_dcf_assumptions


def _market_inputs():
    return MarketInputs(
        risk_free_rate=0.04,
        equity_risk_premium=0.05,
        risk_free_source="Test 10Y Treasury",
        equity_risk_premium_source="Test ERP",
        warnings=[],
    )


def _financials():
    return pd.DataFrame(
        {
            "2024-12-31": [1_000.0, 120.0, 25.0, 21.0],
            "2023-12-31": [900.0, 100.0, 30.0, 18.0],
            "2022-12-31": [800.0, 90.0, 35.0, 17.0],
        },
        index=["Total Revenue", "Pretax Income", "Interest Expense", "Tax Provision"],
    )


def _balance_sheet():
    return pd.DataFrame(
        {
            "2024-12-31": [200.0],
            "2023-12-31": [220.0],
        },
        index=["Total Debt"],
    )


def _cashflow():
    return pd.DataFrame(
        {
            "2024-12-31": [120.0],
            "2023-12-31": [100.0],
            "2022-12-31": [90.0],
        },
        index=["Free Cash Flow"],
    )


def test_estimate_dynamic_dcf_assumptions_uses_wacc_and_growth_inputs():
    info = {"beta": 1.2, "marketCap": 1_800.0}

    estimate = estimate_dynamic_dcf_assumptions(info, _financials(), _balance_sheet(), _cashflow(), _market_inputs())

    assert estimate.assumptions.discount_rate > 0.06
    assert estimate.assumptions.discount_rate < 0.16
    assert estimate.assumptions.growth_rate > 0
    assert estimate.assumptions.growth_rate <= 0.12
    assert estimate.assumptions.terminal_growth_rate <= 0.03
    assert estimate.assumptions.terminal_growth_rate < estimate.assumptions.discount_rate
    assert any(line.assumption == "Cost of equity" for line in estimate.lines)
    assert any(line.assumption == "Discount rate" and line.source == "WACC estimate" for line in estimate.lines)


def test_estimate_dynamic_dcf_assumptions_falls_back_when_inputs_missing():
    estimate = estimate_dynamic_dcf_assumptions({}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), _market_inputs())

    assert estimate.assumptions.growth_rate == 0.03
    assert estimate.assumptions.projection_years == 5
    assert estimate.warnings
    assert any(line.assumption == "Beta" and "Fallback" in line.source for line in estimate.lines)


def test_estimate_dynamic_dcf_assumptions_can_use_quarterly_fcf_growth_when_annual_fcf_missing():
    quarterly_cashflow = pd.DataFrame(
        {
            "2026-09-30": [130.0, -20.0],
            "2026-06-30": [120.0, -20.0],
            "2026-03-31": [110.0, -20.0],
            "2025-12-31": [100.0, -20.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )

    estimate = estimate_dynamic_dcf_assumptions(
        {"beta": 1.0, "marketCap": 1_000.0},
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        _market_inputs(),
        quarterly_cashflow=quarterly_cashflow,
    )

    assert estimate.assumptions.growth_rate > 0
    assert any("quarterly FCF growth" in line.source for line in estimate.lines if line.assumption == "Growth rate")


def test_estimate_dynamic_dcf_assumptions_ignores_non_dataframe_quarterly_cashflow():
    estimate = estimate_dynamic_dcf_assumptions(
        {"beta": 1.0, "marketCap": 1_000.0},
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        _market_inputs(),
        quarterly_cashflow={"unexpected": "shape"},
    )

    assert estimate.assumptions.growth_rate == 0.03
    assert estimate.warnings
