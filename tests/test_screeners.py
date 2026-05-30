from types import SimpleNamespace

import pandas as pd

from analysis import sp500_deals
from analysis import quality_value_screener
from analysis.results import BatchAnalysisResult
from models.valuation import DcfAssumptions


class _Progress:
    def progress(self, value):
        self.value = value


class _Stock:
    info = {
        "currentPrice": 10.0,
        "longName": "Example Co",
        "sharesOutstanding": 100,
    }
    cashflow = pd.DataFrame(
        {
            "2024-12-31": [100.0, 150.0],
            "2023-12-31": [90.0, 90.0],
        },
        index=["Free Cash Flow", "Operating Cash Flow"],
    )
    financials = pd.DataFrame(
        {
            "2024-12-31": [120.0, 1_000.0, 450.0],
            "2023-12-31": [80.0, 900.0, 360.0],
        },
        index=["Net Income", "Total Revenue", "Gross Profit"],
    )
    balance_sheet = pd.DataFrame(
        {
            "2024-12-31": [10.0, 20.0, 1_000.0, 200.0, 500.0, 250.0, 100.0],
            "2023-12-31": [8.0, 25.0, 1_000.0, 250.0, 400.0, 250.0, 110.0],
        },
        index=[
            "Cash And Cash Equivalents",
            "Total Debt",
            "Total Assets",
            "Long Term Debt",
            "Current Assets",
            "Current Liabilities",
            "Ordinary Shares Number",
        ],
    )


def test_sp500_screener_skips_missing_fair_value(monkeypatch):
    monkeypatch.setattr(sp500_deals, "get_sp500_tickers", lambda: ["AAA"])
    monkeypatch.setattr(sp500_deals.st, "progress", lambda value: _Progress())
    monkeypatch.setattr(sp500_deals.yf, "Ticker", lambda ticker: _Stock())
    monkeypatch.setattr(
        sp500_deals,
        "calculate_fair_value",
        lambda *args, **kwargs: SimpleNamespace(fair_value_per_share=None),
    )

    result = sp500_deals.analyze_sp500_deals()

    assert isinstance(result, BatchAnalysisResult)
    assert result.dataframe is None
    assert result.skipped[0].ticker == "AAA"
    assert result.skipped[0].reason == "missing_fair_value_per_share"


def test_sp500_screener_passes_custom_assumptions(monkeypatch):
    custom_assumptions = DcfAssumptions(0.12, 0.04, 0.02, 7)
    captured = {}

    monkeypatch.setattr(sp500_deals, "get_sp500_tickers", lambda: ["AAA"])
    monkeypatch.setattr(sp500_deals.st, "progress", lambda value: _Progress())
    monkeypatch.setattr(sp500_deals.yf, "Ticker", lambda ticker: _Stock())

    def fake_calculate_fair_value(*args, **kwargs):
        captured["assumptions"] = kwargs["assumptions"]
        return SimpleNamespace(fair_value_per_share=15.0)

    monkeypatch.setattr(sp500_deals, "calculate_fair_value", fake_calculate_fair_value)

    result = sp500_deals.analyze_sp500_deals(assumptions=custom_assumptions)

    assert captured["assumptions"] == custom_assumptions
    assert result.dataframe is not None
    assert result.dataframe.iloc[0]["Ticker"] == "AAA"


def test_quality_value_screener_includes_financial_health(monkeypatch):
    custom_assumptions = DcfAssumptions(0.10, 0.03, 0.02, 5)

    monkeypatch.setattr(quality_value_screener, "get_tickers", lambda universe, uploaded_file: ["AAA"])
    monkeypatch.setattr(quality_value_screener.st.sidebar, "subheader", lambda label: None)
    monkeypatch.setattr(quality_value_screener.st.sidebar, "selectbox", lambda *args, **kwargs: "Dow 30")
    monkeypatch.setattr(quality_value_screener.st.sidebar, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(quality_value_screener.st, "progress", lambda value: _Progress())
    monkeypatch.setattr(quality_value_screener.yf, "Ticker", lambda ticker: _Stock())
    monkeypatch.setattr(
        quality_value_screener,
        "add_sec_fallback_to_statements",
        lambda ticker, financials, balance_sheet, cashflow: (
            financials,
            balance_sheet,
            cashflow,
            "Yahoo Finance",
            [],
        ),
    )
    monkeypatch.setattr(
        quality_value_screener,
        "calculate_fair_value",
        lambda *args, **kwargs: SimpleNamespace(fair_value_per_share=15.0),
    )

    result = quality_value_screener.analyze_quality_value_screener(assumptions=custom_assumptions)

    assert result.dataframe is not None
    row = result.dataframe.iloc[0]
    assert row["Financial Health Raw Score"] == 9
    assert row["Financial Health Available Signals"] == 9
    assert row["Financial Health Score"] == 1
    assert "Positive ROA: Pass" in row["Financial Health Details"]
