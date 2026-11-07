"""Worked examples loaded into the review editor on request."""

from dataclasses import replace

from models.investment_review import CashFlowAdjustment, InvestmentReview, ReviewCase
from models.valuation import DcfAssumptions

DECK_QUARTER = "https://ir.deckers.com/sec-filings/all-sec-filings/content/0001628280-26-068116/deck-20260930.htm"
DECK_ANNUAL = "https://www.sec.gov/Archives/edgar/data/910521/000162828026037664/deck-20260331.htm"
DECK_RESULTS = "https://ir.deckers.com/news-events/press-releases/detail/666/deckers-brands-reports-second-quarter-fiscal-year-2027-financial-results"


def worked_review(ticker: str, draft: InvestmentReview) -> InvestmentReview:
    if ticker == "DECK":
        return InvestmentReview(
            ticker="DECK", position=draft.position,
            reported_fcf=1_052_593_000,
            fcf_basis=f"TTM through Sep 30, 2026. FY 2026 plus current H1 less prior H1. {DECK_ANNUAL} {DECK_QUARTER}",
            net_debt=-1_210_000_000, shares=133_479_987, safety_margin=0.20,
            cases={
                "Bear": ReviewCase(-117_542_000, DcfAssumptions(0.11, 0, 0.02, 5)),
                "Base": ReviewCase(0, DcfAssumptions(0.10, 0.03, 0.02, 5)),
                "Bull": ReviewCase(132_458_000, DcfAssumptions(0.10, 0.05, 0.02, 5)),
            },
            adjustments=[
                CashFlowAdjustment("Tariff refund and related interest, cash received", -49_000_000, DECK_RESULTS),
                CashFlowAdjustment("Estimated economic cost of TTM stock compensation", -46_051_000, DECK_QUARTER),
                CashFlowAdjustment("Estimated after-tax interest on cash valued separately", -40_000_000, DECK_ANNUAL),
            ],
            thesis="HOKA and UGG can generate cash through multiple product cycles if full-price demand holds.",
            evidence=f"Quarter ended Sep 30, 2026. HOKA sales +6.8%, UGG +3.5%, DTC comparable sales −6.4%. {DECK_RESULTS}",
            reconsider_if="Sustained weakness in full-price demand or operating margins after removing one-time items.",
        )
    if ticker == "AMAT":
        cash_flow = draft.reported_fcf or 0
        return replace(
            draft,
            cases={
                "Bear": ReviewCase(-0.20 * cash_flow, DcfAssumptions(0.11, 0, 0.02, 5)),
                "Base": ReviewCase(0, DcfAssumptions(0.10, 0.03, 0.02, 5)),
                "Bull": ReviewCase(0.20 * cash_flow, DcfAssumptions(0.10, 0.06, 0.02, 5)),
            },
            thesis="Evaluate whether process expertise and the equipment installed base support durable cash generation through a downturn.",
            evidence="Illustrative cycle stress test. Replace reported cash flow with a sourced mid-cycle estimate and check margins and service revenue across multiple years.",
            reconsider_if="A sustained loss of process position or weaker cash conversion through the next equipment cycle.",
        )
    return draft
