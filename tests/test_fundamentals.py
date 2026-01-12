import pandas as pd

from utils.fundamentals import extract_fundamentals
from models.valuation import calculate_fair_value


def _sample_balance_sheet():
    return pd.DataFrame(
        {
            "2024-12-31": [100.0, 20.0, 80.0],
        },
        index=[
            "Cash And Cash Equivalents",
            "Short Long Term Debt",
            "Long Term Debt",
        ],
    )


def _sample_cashflow():
    return pd.DataFrame({"2024-12-31": [100.0]}, index=["Free Cash Flow"])


def test_extract_fundamentals_sums_debt_components():
    info = {"sharesOutstanding": 1_000_000}
    snapshot = extract_fundamentals(info, _sample_balance_sheet())

    assert snapshot.total_debt == 100.0
    assert snapshot.cash_and_equivalents == 100.0
    assert snapshot.net_debt == 0.0
    assert snapshot.debt_source == "Long Term Debt + Short Term Debt"


def test_extract_fundamentals_warns_when_shares_missing():
    snapshot = extract_fundamentals({}, _sample_balance_sheet())

    assert snapshot.shares_outstanding is None
    assert any("per-share" in warning.lower() for warning in snapshot.warnings)


def test_calculate_fair_value_handles_missing_shares():
    result = calculate_fair_value(_sample_cashflow(), net_debt=0.0, shares_outstanding=None)

    assert result is not None
    assert result.enterprise_value is not None
    assert result.fair_value_per_share is None
