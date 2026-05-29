from types import SimpleNamespace

import pandas as pd

from analysis import sp500_deals
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
    cashflow = pd.DataFrame({"2024-12-31": [100.0]}, index=["Free Cash Flow"])
    balance_sheet = pd.DataFrame(
        {"2024-12-31": [10.0, 20.0]},
        index=["Cash And Cash Equivalents", "Total Debt"],
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
