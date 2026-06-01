import pandas as pd

from data.sec_facts import (
    SecFinancialStatements,
    add_sec_fallback_to_statements,
    merge_statement_frame,
    sec_headers,
    statements_from_companyfacts,
    ticker_to_cik,
)


def _fact(values, unit="USD"):
    return {"units": {unit: values}}


def _annual_value(end, value, tag_form="10-K"):
    return {
        "end": end,
        "val": value,
        "fy": int(end[:4]),
        "fp": "FY",
        "form": tag_form,
        "filed": f"{int(end[:4]) + 1}-02-01",
    }


def _companyfacts():
    return {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": _fact([
                    _annual_value("2024-12-31", 120),
                    _annual_value("2023-12-31", 80),
                ]),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _fact([
                    _annual_value("2024-12-31", 1000),
                    _annual_value("2023-12-31", 900),
                ]),
                "GrossProfit": _fact([
                    _annual_value("2024-12-31", 450),
                    _annual_value("2023-12-31", 360),
                ]),
                "Assets": _fact([
                    _annual_value("2024-12-31", 1000),
                    _annual_value("2023-12-31", 1000),
                ]),
                "LongTermDebtNoncurrent": _fact([
                    _annual_value("2024-12-31", 200),
                    _annual_value("2023-12-31", 250),
                ]),
                "AssetsCurrent": _fact([
                    _annual_value("2024-12-31", 500),
                    _annual_value("2023-12-31", 400),
                ]),
                "LiabilitiesCurrent": _fact([
                    _annual_value("2024-12-31", 250),
                    _annual_value("2023-12-31", 250),
                ]),
                "EntityCommonStockSharesOutstanding": _fact([
                    _annual_value("2024-12-31", 100),
                    _annual_value("2023-12-31", 110),
                ], unit="shares"),
                "NetCashProvidedByUsedInOperatingActivities": _fact([
                    _annual_value("2024-12-31", 150),
                    _annual_value("2023-12-31", 90),
                ]),
            }
        }
    }


def test_statements_from_companyfacts_normalizes_financial_health_fields():
    statements = statements_from_companyfacts(_companyfacts(), cik="0000320193")

    assert statements.financials.loc["Net Income", "2024-12-31"] == 120
    assert statements.financials.loc["Total Revenue", "2024-12-31"] == 1000
    assert statements.balance_sheet.loc["Total Assets", "2024-12-31"] == 1000
    assert statements.balance_sheet.loc["Ordinary Shares Number", "2024-12-31"] == 100
    assert statements.cashflow.loc["Operating Cash Flow", "2024-12-31"] == 150
    assert "SEC EDGAR fallback" in statements.source_note


def test_merge_statement_frame_preserves_yahoo_values_and_fills_missing_sec_values():
    yahoo = pd.DataFrame({"2024-12-31": [120.0]}, index=["Net Income"])
    sec = pd.DataFrame({"2024-12-31": [130.0, 1000.0]}, index=["Net Income", "Total Revenue"])

    merged = merge_statement_frame(yahoo, sec)

    assert merged.loc["Net Income", "2024-12-31"] == 120.0
    assert merged.loc["Total Revenue", "2024-12-31"] == 1000.0


def test_add_sec_fallback_skips_sec_when_yahoo_has_all_signals(monkeypatch):
    called = False

    def fake_get_sec_financial_health_statements(ticker):
        nonlocal called
        called = True
        raise AssertionError("SEC fallback should not be called")

    monkeypatch.setattr(
        "data.sec_facts.get_sec_financial_health_statements",
        fake_get_sec_financial_health_statements,
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
            "2024-12-31": [1_000.0, 200.0, 500.0, 250.0, 100.0],
            "2023-12-31": [1_000.0, 250.0, 400.0, 250.0, 110.0],
        },
        index=[
            "Total Assets",
            "Long Term Debt",
            "Current Assets",
            "Current Liabilities",
            "Ordinary Shares Number",
        ],
    )
    cashflow = pd.DataFrame(
        {
            "2024-12-31": [150.0],
            "2023-12-31": [90.0],
        },
        index=["Operating Cash Flow"],
    )

    _, _, _, source, warnings = add_sec_fallback_to_statements("AAPL", financials, balance_sheet, cashflow)

    assert not called
    assert source == "Yahoo Finance"
    assert warnings == []


def test_sec_headers_allow_configurable_user_agent(monkeypatch):
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "StockMarketTools Test test@example.com")

    headers = sec_headers()

    assert headers["User-Agent"] == "StockMarketTools Test test@example.com"
    assert headers["Accept"] == "application/json"


def test_ticker_to_cik_uses_static_common_ticker_map_without_sec_request(monkeypatch):
    monkeypatch.setattr(
        "data.sec_facts._ticker_to_cik_map",
        lambda: (_ for _ in ()).throw(AssertionError("SEC ticker map should not be requested")),
    )

    assert ticker_to_cik("AAPL") == "0000320193"


def test_add_sec_fallback_suppresses_warning_when_sec_supplies_no_data(monkeypatch):
    monkeypatch.setattr(
        "data.sec_facts.get_sec_financial_health_statements",
        lambda ticker: SecFinancialStatements(warnings=["SEC EDGAR fallback failed for AAPL: 403"]),
    )

    financials = pd.DataFrame({"2024-12-31": [120.0]}, index=["Net Income"])
    balance_sheet = pd.DataFrame({"2024-12-31": [1_000.0]}, index=["Total Assets"])
    cashflow = pd.DataFrame({"2024-12-31": [150.0]}, index=["Operating Cash Flow"])

    _, _, _, source, warnings = add_sec_fallback_to_statements("AAPL", financials, balance_sheet, cashflow)

    assert source == "Yahoo Finance"
    assert warnings == []
