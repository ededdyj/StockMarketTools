import pandas as pd

from models.free_cash_flow import (
    calculate_free_cash_flow,
    resolve_free_cash_flow,
    snapshot_from_sec_companyfacts,
)


def test_calculate_free_cash_flow_handles_negative_capex_convention():
    assert calculate_free_cash_flow(10_000, -2_000) == 8_000


def test_calculate_free_cash_flow_handles_positive_capex_convention():
    assert calculate_free_cash_flow(10_000, 2_000) == 8_000


def test_resolve_free_cash_flow_prefers_operating_cash_flow_minus_capex():
    cashflow = pd.DataFrame(
        {"2024-12-31": [10_000.0, -2_000.0, 7_000.0]},
        index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"],
    )

    snapshot = resolve_free_cash_flow(cashflow)

    assert snapshot.value == 8_000
    assert snapshot.operating_cash_flow == 10_000
    assert snapshot.capital_expenditures == -2_000
    assert "operating cash flow" in snapshot.source.lower()


def test_resolve_free_cash_flow_three_year_average():
    cashflow = pd.DataFrame(
        {
            "2024-12-31": [12_000.0, -2_000.0],
            "2023-12-31": [9_000.0, -1_000.0],
            "2022-12-31": [7_000.0, -1_000.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )

    snapshot = resolve_free_cash_flow(cashflow, method="three_year_average")

    assert snapshot.value == 8_000
    assert snapshot.method == "three_year_average"


def test_resolve_free_cash_flow_prefers_sec_ttm_over_stale_annual():
    annual = pd.DataFrame(
        {"2025-09-27": [100_000.0, -10_000.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    sec_snapshot = snapshot_from_sec_companyfacts(
        {
            "facts": {
                "us-gaap": {
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {
                            "USD": [
                                _sec_fact("2024-09-29", "2025-09-27", 100_000.0, "FY", 2025, "10-K"),
                                _sec_fact("2024-09-29", "2025-06-28", 75_000.0, "Q3", 2025, "10-Q"),
                                _sec_fact("2025-09-28", "2026-06-27", 90_000.0, "Q3", 2026, "10-Q"),
                            ]
                        }
                    },
                    "PaymentsToAcquirePropertyPlantAndEquipment": {
                        "units": {
                            "USD": [
                                _sec_fact("2024-09-29", "2025-09-27", 10_000.0, "FY", 2025, "10-K"),
                                _sec_fact("2024-09-29", "2025-06-28", 7_000.0, "Q3", 2025, "10-Q"),
                                _sec_fact("2025-09-28", "2026-06-27", 9_000.0, "Q3", 2026, "10-Q"),
                            ]
                        }
                    },
                }
            }
        },
        cik="0000320193",
    )

    snapshot = resolve_free_cash_flow(annual, method="best_available", sec_fcf_snapshot=sec_snapshot)

    assert snapshot.value == 103_000
    assert snapshot.method == "ttm"
    assert "SEC Companyfacts TTM" in snapshot.source
    assert "2026-06-27" in snapshot.period


def test_resolve_free_cash_flow_uses_yfinance_quarterly_ttm_before_annual_fallback():
    annual = pd.DataFrame(
        {"2025-12-31": [100.0, -10.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    quarterly = pd.DataFrame(
        {
            "2026-09-30": [30.0, -4.0],
            "2026-06-30": [28.0, -3.0],
            "2026-03-31": [26.0, -2.0],
            "2025-12-31": [24.0, -1.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )

    snapshot = resolve_free_cash_flow(annual, method="best_available", quarterly_cashflow=quarterly)

    assert snapshot.value == 98.0
    assert snapshot.method == "ttm"
    assert snapshot.source == "yfinance quarterly cashflow TTM"


def test_resolve_free_cash_flow_annual_fallback_when_quarterly_missing():
    annual = pd.DataFrame(
        {"2025-12-31": [100.0, -10.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )

    snapshot = resolve_free_cash_flow(annual, method="best_available")

    assert snapshot.value == 90.0
    assert snapshot.method == "ttm"
    assert "annual fallback" in snapshot.source
    assert any("using latest fiscal-year FCF" in warning for warning in snapshot.warnings)


def test_resolve_free_cash_flow_yfinance_quarterly_handles_negative_capex():
    quarterly = pd.DataFrame(
        {
            "2026-09-30": [10.0, -4.0],
            "2026-06-30": [10.0, -3.0],
            "2026-03-31": [10.0, -2.0],
            "2025-12-31": [10.0, -1.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )

    snapshot = resolve_free_cash_flow(pd.DataFrame(), method="best_available", quarterly_cashflow=quarterly)

    assert snapshot.value == 30.0
    assert snapshot.operating_cash_flow == 40.0
    assert snapshot.capital_expenditures == -10.0


def test_resolve_free_cash_flow_ignores_non_dataframe_optional_inputs():
    annual = pd.DataFrame(
        {"2025-12-31": [100.0, -10.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )

    snapshot = resolve_free_cash_flow(
        annual,
        method="best_available",
        quarterly_cashflow={"not": "a dataframe"},
        ttm_cashflow=object(),
    )

    assert snapshot.value == 90.0
    assert "annual fallback" in snapshot.source


def _sec_fact(start, end, value, fp, fy, form):
    return {
        "start": start,
        "end": end,
        "val": value,
        "fp": fp,
        "fy": fy,
        "form": form,
        "filed": end,
    }
