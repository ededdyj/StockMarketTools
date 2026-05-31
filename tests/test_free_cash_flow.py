import pandas as pd

from models.free_cash_flow import calculate_free_cash_flow, resolve_free_cash_flow


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
