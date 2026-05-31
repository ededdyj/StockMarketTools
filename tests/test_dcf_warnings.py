import pandas as pd

from models.dcf_warnings import generate_dcf_warnings
from models.free_cash_flow import FreeCashFlowSnapshot
from models.valuation import DcfAssumptions
from utils.fundamentals import extract_fundamentals


def test_generate_dcf_warnings_flags_yield_payout_and_assumption_risk():
    info = {
        "dividendYield": 0.20,
        "payoutRatio": 1.2,
        "sharesOutstanding": 100_000_000,
        "marketCap": 10_000_000_000,
        "currentPrice": 100,
    }
    fundamentals = extract_fundamentals(info, pd.DataFrame())
    fcf = FreeCashFlowSnapshot(
        value=-100.0,
        source="Test",
        period="2024",
        formula="Free cash flow = operating cash flow - abs(capex)",
    )

    warnings = generate_dcf_warnings(
        info,
        fundamentals,
        DcfAssumptions(0.04, 0.12, 0.025, 5),
        fcf,
    )
    messages = " ".join(warning.message for warning in warnings)

    assert "Dividend yield" in messages
    assert "Payout ratio" in messages
    assert "Starting free cash flow is non-positive" in messages
    assert "less than terminal growth + 2%" in messages


def test_generate_dcf_warnings_flags_share_mismatch():
    info = {
        "sharesOutstanding": 325_000_000,
        "marketCap": 65_000_000_000,
        "currentPrice": 100,
    }
    fundamentals = extract_fundamentals(info, pd.DataFrame())
    fcf = FreeCashFlowSnapshot(
        value=1_000.0,
        source="Test",
        period="2024",
        formula="Free cash flow = operating cash flow - abs(capex)",
    )

    warnings = generate_dcf_warnings(
        info,
        fundamentals,
        DcfAssumptions(0.10, 0.03, 0.02, 5),
        fcf,
    )

    assert any(warning.category == "Shares" for warning in warnings)
