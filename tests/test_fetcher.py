import pandas as pd

from data import fetcher


class FakeTicker:
    info = {"symbol": "AAPL"}
    financials = pd.DataFrame()
    cashflow = pd.DataFrame()
    quarterly_cashflow = pd.DataFrame()
    ttm_cashflow = pd.DataFrame()
    balance_sheet = pd.DataFrame()

    def history(self, **kwargs):
        return pd.DataFrame({"Close": [100.0]})


def test_get_stock_data_keeps_sec_fcf_warnings_separate(monkeypatch):
    monkeypatch.setattr(fetcher.yf, "Ticker", lambda ticker: FakeTicker())
    monkeypatch.setattr(
        fetcher,
        "get_sec_free_cash_flow_snapshot",
        lambda ticker: (None, ["SEC EDGAR FCF lookup failed for AAPL: 403"]),
    )
    monkeypatch.setattr(
        fetcher,
        "add_sec_fallback_to_statements",
        lambda ticker, financials, balance_sheet, cashflow: (
            financials,
            balance_sheet,
            cashflow,
            "Yahoo Finance",
            [],
        ),
    )

    data = fetcher.get_stock_data("AAPL")

    assert data["sec_warnings"] == []
    assert data["sec_fcf_warnings"] == ["SEC EDGAR FCF lookup failed for AAPL: 403"]
