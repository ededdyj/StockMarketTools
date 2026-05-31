"""DCF suitability scoring for single-stock valuation."""

from __future__ import annotations

from dataclasses import dataclass, field

from models.dcf_warnings import DcfWarning
from models.free_cash_flow import FreeCashFlowSnapshot
from utils.fundamentals import FundamentalsSnapshot


LOW_FIT_KEYWORDS = ["bank", "insurance", "insurer", "reit", "fund", "etf"]
CYCLICAL_KEYWORDS = ["hardware", "semiconductor", "automotive", "airline", "energy", "commodity"]


@dataclass(frozen=True)
class DcfFitResult:
    label: str
    score: int
    reasons: list[str] = field(default_factory=list)


def calculate_dcf_fit(
    info: dict,
    fundamentals: FundamentalsSnapshot,
    fcf_snapshot: FreeCashFlowSnapshot,
    warnings: list[DcfWarning],
) -> DcfFitResult:
    """Return a simple DCF suitability label for interpreting valuation output."""

    score = 100
    reasons: list[str] = []
    sector = str(info.get("sector", "")).lower()
    industry = str(info.get("industry", "")).lower()
    quote_type = str(info.get("quoteType", "")).lower()
    text = " ".join([sector, industry, quote_type])

    if any(keyword in text for keyword in LOW_FIT_KEYWORDS):
        score -= 45
        reasons.append("Business type often requires a specialized valuation model rather than a standard FCF DCF.")

    if any(keyword in text for keyword in CYCLICAL_KEYWORDS):
        score -= 15
        reasons.append("Industry can be cyclical, so normalized FCF and scenario analysis matter.")

    if fcf_snapshot.value is None:
        score -= 50
        reasons.append("Starting FCF is missing.")
    elif fcf_snapshot.value <= 0:
        score -= 40
        reasons.append("Starting FCF is negative or zero.")

    if fundamentals.share_resolution and fundamentals.share_resolution.data_quality_risk:
        score -= 20
        reasons.append("Share-count resolver marked valuation as data-quality risk.")

    high_warnings = [warning for warning in warnings if warning.severity == "High"]
    medium_warnings = [warning for warning in warnings if warning.severity == "Medium"]
    if high_warnings:
        score -= min(35, 12 * len(high_warnings))
        reasons.append(f"{len(high_warnings)} high-severity valuation warning(s) are present.")
    if medium_warnings:
        score -= min(20, 4 * len(medium_warnings))
        reasons.append(f"{len(medium_warnings)} medium-severity valuation warning(s) are present.")

    if not fundamentals.debt_source or not fundamentals.cash_source:
        score -= 10
        reasons.append("Cash or debt fields required fallbacks.")

    score = max(0, min(100, score))
    if score >= 75:
        label = "High"
    elif score >= 45:
        label = "Medium"
    else:
        label = "Low"

    if not reasons:
        reasons.append("Positive FCF, usable debt/cash, reliable shares, and no major DCF warnings.")

    return DcfFitResult(label=label, score=score, reasons=reasons)
