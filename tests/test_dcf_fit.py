from models.dcf_fit import calculate_dcf_fit
from models.dcf_warnings import DcfWarning
from models.free_cash_flow import FreeCashFlowSnapshot
from utils.fundamentals import FundamentalsSnapshot


def _fundamentals():
    return FundamentalsSnapshot(
        cash_and_equivalents=10,
        total_debt=30,
        net_debt=20,
        shares_outstanding=100,
        balance_sheet_as_of="2026-01-31",
        pulled_at="2026-05-31 00:00:00 UTC",
        cash_source="Cash And Cash Equivalents",
        debt_source="Total Debt",
        shares_source="Filing-derived diluted weighted-average shares",
    )


def test_dcf_fit_high_for_stable_positive_fcf_with_clean_inputs():
    fit = calculate_dcf_fit(
        {"sector": "Technology", "industry": "Software"},
        _fundamentals(),
        FreeCashFlowSnapshot(100, "Test", "2026-01-31", "FCF formula"),
        [],
    )

    assert fit.label == "High"
    assert fit.score >= 75


def test_dcf_fit_low_for_negative_fcf_and_nonstandard_model():
    fit = calculate_dcf_fit(
        {"sector": "Financial Services", "industry": "Insurance"},
        _fundamentals(),
        FreeCashFlowSnapshot(-100, "Test", "2026-01-31", "FCF formula"),
        [DcfWarning("High", "FCF", "Negative FCF")],
    )

    assert fit.label == "Low"
    assert any("specialized valuation" in reason for reason in fit.reasons)
