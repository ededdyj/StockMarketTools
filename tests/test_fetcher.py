import pandas as pd

from data import fetcher


class FakeTicker:
    info = {"symbol": "AAPL"}
    financials = pd.DataFrame()
    quarterly_financials = pd.DataFrame({"2026-03-31": [100.0]}, index=["Total Revenue"])
    cashflow = pd.DataFrame()
    quarterly_cashflow = pd.DataFrame()
    ttm_cashflow = pd.DataFrame()
    balance_sheet = pd.DataFrame()
    quarterly_balance_sheet = pd.DataFrame({"2026-03-31": [50.0]}, index=["Cash And Cash Equivalents"])

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
    assert "quarterly_financials" in data
    assert "quarterly_balance_sheet" in data
