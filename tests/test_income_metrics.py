import pandas as pd

from models.income_metrics import resolve_income_metrics


def test_resolve_income_metrics_prefers_quarterly_ttm():
    quarterly = pd.DataFrame(
        {
            "2026-03-31": [120.0, 30.0],
            "2025-12-31": [110.0, 25.0],
            "2025-09-30": [100.0, 20.0],
            "2025-06-30": [90.0, 15.0],
        },
        index=["Total Revenue", "Net Income"],
    )

    snapshot = resolve_income_metrics({}, quarterly_financials=quarterly, shares_outstanding=10.0)

    assert snapshot.revenue == 420.0
    assert snapshot.net_income == 90.0
    assert snapshot.eps == 9.0
    assert snapshot.source == "yfinance quarterly financials TTM"
    assert snapshot.period == "TTM through 2026-03-31"


def test_resolve_income_metrics_falls_back_to_annual_financials():
    annual = pd.DataFrame(
        {"2025-09-30": [400.0, 80.0]},
        index=["Total Revenue", "Net Income"],
    )

    snapshot = resolve_income_metrics({}, annual_financials=annual, shares_outstanding=20.0)

    assert snapshot.revenue == 400.0
    assert snapshot.net_income == 80.0
    assert snapshot.eps == 4.0
    assert snapshot.source == "yfinance annual financials fallback"


def test_resolve_income_metrics_uses_profile_when_statements_missing():
    snapshot = resolve_income_metrics(
        {"totalRevenue": 100.0, "netIncomeToCommon": 10.0, "trailingEps": 2.0}
    )

    assert snapshot.revenue == 100.0
    assert snapshot.net_income == 10.0
    assert snapshot.eps == 2.0
    assert snapshot.source == "Yahoo Finance profile fallback"
