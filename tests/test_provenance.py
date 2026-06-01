import pandas as pd

from data.market_inputs import MarketInputs
from models.dcf_assumptions import AssumptionLine, DynamicDcfEstimate
from models.free_cash_flow import FreeCashFlowSnapshot
from models.income_metrics import IncomeMetricsSnapshot
from models.provenance import (
    age_in_days,
    build_valuation_input_provenance,
    freshness_label,
    parse_date,
)
from models.valuation import DcfAssumptions
from utils.fundamentals import FundamentalsSnapshot


def test_parse_date_age_and_freshness_labels():
    assert parse_date("2026-01-31") is not None
    assert parse_date("TTM through 2026-06-27") == pd.Timestamp("2026-06-27")
    assert parse_date("not-a-date") is None
    now = pd.Timestamp("2026-05-31")
    assert age_in_days("2026-05-01", now=now) == 30
    assert freshness_label(30) == "Fresh"
    assert freshness_label(90) == "Recent"
    assert freshness_label(200) == "Stale"
    assert freshness_label(500) == "Very stale"
    assert freshness_label(None) == "Unknown"


def test_build_valuation_input_provenance_includes_categories_and_stale_warning():
    fundamentals = FundamentalsSnapshot(
        cash_and_equivalents=10,
        total_debt=30,
        net_debt=20,
        shares_outstanding=100,
        balance_sheet_as_of="2025-01-31",
        pulled_at="2026-05-31 00:00:00 UTC",
        cash_source="Cash And Cash Equivalents",
        debt_source="Total Debt",
        shares_source="Filing-derived diluted weighted-average shares",
        shares_date_or_period="2025-01-31",
    )
    fcf = FreeCashFlowSnapshot(
        value=100,
        source="Yahoo Finance operating cash flow and capital expenditures",
        period="2025-01-31",
        formula="Free cash flow = operating cash flow - abs(capital expenditures)",
        operating_cash_flow=120,
        capital_expenditures=-20,
    )
    dynamic = DynamicDcfEstimate(
        assumptions=DcfAssumptions(0.10, 0.03, 0.02, 5),
        lines=[
            AssumptionLine("Risk-free rate", 0.045, "FRED DGS10 10Y Treasury (2026-05-30)", "Latest long-term US Treasury proxy"),
            AssumptionLine("Equity risk premium", 0.05, "Damodaran historical implied ERP table (2026)", "Market-implied ERP"),
            AssumptionLine("Discount rate", 0.10, "WACC estimate", "Weighted cost of capital"),
            AssumptionLine("Growth rate", 0.03, "Recent growth blend", "Recent growth"),
            AssumptionLine("Terminal growth", 0.02, "Conservative terminal cap", "Terminal cap"),
        ],
        warnings=[],
    )

    report = build_valuation_input_provenance(
        {"currentPrice": 10, "marketCap": 1000, "beta": 1.0},
        fundamentals,
        fcf,
        dynamic,
        MarketInputs(0.045, 0.05, "FRED DGS10 10Y Treasury (2026-05-30)", "Damodaran historical implied ERP table (2026)", []),
        financials=pd.DataFrame({"2025-01-31": [500]}, index=["Total Revenue"]),
        income_metrics=IncomeMetricsSnapshot(
            revenue=600,
            net_income=120,
            eps=1.2,
            source="yfinance quarterly financials TTM",
            period="TTM through 2026-03-31",
            method="ttm_quarterly",
            confidence_level="Medium",
        ),
    )

    names = {row.name for row in report.rows}
    assert "Current Price" in names
    assert "Free Cash Flow" in names
    assert "Risk-free Rate" in names
    revenue = next(row for row in report.rows if row.name == "Revenue")
    assert revenue.value == 600
    assert revenue.period_or_as_of == "TTM through 2026-03-31"
    assert any(row.category == "Official filing data" for row in report.rows)
    assert any("more than 120 days old" in warning for warning in report.warnings)
