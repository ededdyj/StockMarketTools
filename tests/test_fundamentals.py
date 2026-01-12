import pandas as pd

from utils.fundamentals import extract_fundamentals
from models.valuation import calculate_fair_value


def _multi_period_balance_sheet():
    return pd.DataFrame(
        {
            "2022-12-31": [50.0, 10.0, 40.0],
            "2024-12-31": [120.0, 30.0, 90.0],
            "2023-12-31": [90.0, 20.0, 70.0],
        },
        index=[
            "Cash And Cash Equivalents",
            "Short Long Term Debt",
            "Long Term Debt",
        ],
    )


def _string_column_balance_sheet():
    return pd.DataFrame(
        {
            "FY2024": [75.0, 10.0, 50.0],
        },
        index=[
            "Cash And Cash Equivalents",
            "Short Long Term Debt",
            "Long Term Debt",
        ],
    )


def _sample_cashflow():
    return pd.DataFrame({"2024-12-31": [100.0]}, index=["Free Cash Flow"])


def test_extract_fundamentals_uses_latest_balance_sheet_column():
    info = {"sharesOutstanding": 1_000_000}
    snapshot = extract_fundamentals(info, _multi_period_balance_sheet())

    assert snapshot.balance_sheet_as_of == "2024-12-31"
    # Latest column has cash 120 and debt 30+90=120
    assert snapshot.cash_and_equivalents == 120.0
    assert snapshot.total_debt == 120.0
    assert snapshot.net_debt == 0.0


def test_extract_fundamentals_handles_string_balance_sheet_columns():
    snapshot = extract_fundamentals({"sharesOutstanding": 5_000_000}, _string_column_balance_sheet())

    assert snapshot.balance_sheet_as_of == "FY2024"
    assert snapshot.cash_and_equivalents == 75.0


def test_extract_fundamentals_marks_missing_shares():
    info = {"sharesOutstanding": 0, "impliedSharesOutstanding": 0}
    snapshot = extract_fundamentals(info, _multi_period_balance_sheet())

    assert snapshot.shares_outstanding is None
    assert "MISSING_SHARES" in snapshot.note_tags


def test_calculate_fair_value_net_cash_increases_equity():
    result = calculate_fair_value(_sample_cashflow(), net_debt=-50.0, shares_outstanding=1_000_000)

    assert result is not None
    assert result.equity_value > result.enterprise_value


def test_calculate_fair_value_disables_per_share_when_shares_invalid():
    result = calculate_fair_value(_sample_cashflow(), net_debt=0.0, shares_outstanding=0)

    assert result is not None
    assert result.fair_value_per_share is None
