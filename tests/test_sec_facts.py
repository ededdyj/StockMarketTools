import pandas as pd

from data.sec_facts import merge_statement_frame, statements_from_companyfacts


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
