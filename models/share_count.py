"""Share-count resolution and diagnostics for per-share valuation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


MISMATCH_WARNING_THRESHOLD = 0.10
MISMATCH_RISK_THRESHOLD = 0.25
DOUBLE_HALVE_THRESHOLD = 2.0
STALE_FILING_SHARE_DAYS = 120

YFINANCE_SHARE_FIELDS = [
    ("sharesOutstanding", "Yahoo Finance sharesOutstanding"),
    ("impliedSharesOutstanding", "Yahoo Finance impliedSharesOutstanding"),
]

DILUTED_SHARE_LABELS = [
    "Diluted Average Shares",
    "Diluted Shares",
    "Weighted Average Diluted Shares Outstanding",
]

COMMON_SHARE_LABELS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock Shares Outstanding",
]

FILING_DILUTED_SOURCE = "Filing-derived diluted weighted-average shares"
FILING_COMMON_SOURCE = "Filing-derived period-end common/ordinary shares"


@dataclass(frozen=True)
class ShareCountCandidate:
    value: float
    source: str
    date_or_period: Optional[str]
    kind: str
    formula: str
    warning: Optional[str] = None


@dataclass(frozen=True)
class ShareCountResolution:
    selected_shares: Optional[float]
    selected_shares_source: Optional[str]
    selected_shares_date_or_period: Optional[str]
    implied_shares_from_market_cap: Optional[float]
    selected_vs_implied_pct_diff: Optional[float]
    candidates: list[ShareCountCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_quality_risk: bool = False


def _clean_positive(value) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _latest_column(frame: Optional[pd.DataFrame]) -> tuple[object, Optional[str]]:
    if frame is None or frame.empty:
        return None, None
    columns = list(frame.columns)
    parsed = pd.to_datetime(columns, errors="coerce")
    parsed_series = pd.Series(parsed)
    if parsed_series.notna().any():
        idx = parsed_series.idxmax()
        return columns[idx], parsed_series.iloc[idx].strftime("%Y-%m-%d")
    return columns[0], str(columns[0])


def _value_from_frame(frame: Optional[pd.DataFrame], labels: list[str]) -> tuple[Optional[float], Optional[str]]:
    column, period = _latest_column(frame)
    if column is None:
        return None, None
    for label in labels:
        if label in frame.index and column in frame.columns:
            return _clean_positive(frame.at[label, column]), period
    return None, None


def _pct_diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if not a or not b:
        return None
    return abs(float(a) - float(b)) / max(abs(float(b)), 1.0)


def _candidate_priority(candidate: ShareCountCandidate) -> int:
    order = {
        "filing_diluted": 0,
        "filing_common": 1,
        "yfinance_shares": 2,
        "yfinance_implied": 3,
        "computed_market_cap": 4,
    }
    return order.get(candidate.kind, 9)


def _age_days(value: Optional[str]) -> Optional[int]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    now = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    parsed = pd.Timestamp(parsed)
    if parsed.tzinfo:
        parsed = parsed.tz_localize(None)
    return max((now - parsed).days, 0)


def resolve_share_count(
    info: dict,
    balance_sheet: Optional[pd.DataFrame] = None,
    financials: Optional[pd.DataFrame] = None,
    current_price: Optional[float] = None,
    market_cap: Optional[float] = None,
) -> ShareCountResolution:
    """Resolve shares used for valuation while surfacing conflicting sources."""

    candidates: list[ShareCountCandidate] = []
    warnings: list[str] = []

    diluted, diluted_period = _value_from_frame(financials, DILUTED_SHARE_LABELS)
    if diluted:
        candidates.append(
            ShareCountCandidate(
                value=diluted,
                source=FILING_DILUTED_SOURCE,
                date_or_period=diluted_period,
                kind="filing_diluted",
                formula="Latest diluted average shares from income statement",
            )
        )

    common, common_period = _value_from_frame(balance_sheet, COMMON_SHARE_LABELS)
    if common:
        candidates.append(
            ShareCountCandidate(
                value=common,
                source=FILING_COMMON_SOURCE,
                date_or_period=common_period,
                kind="filing_common",
                formula="Latest common/ordinary shares from balance sheet or SEC companyfacts",
            )
        )

    for field, source in YFINANCE_SHARE_FIELDS:
        value = _clean_positive(info.get(field))
        if value:
            candidates.append(
                ShareCountCandidate(
                    value=value,
                    source=source,
                    date_or_period="Latest Yahoo profile field",
                    kind="yfinance_implied" if field == "impliedSharesOutstanding" else "yfinance_shares",
                    formula=field,
                )
            )

    current_price = _clean_positive(current_price or info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    market_cap = _clean_positive(market_cap or info.get("marketCap"))
    implied_shares = None
    if current_price and market_cap:
        implied_shares = market_cap / current_price
        candidates.append(
            ShareCountCandidate(
                value=implied_shares,
                source="Computed from market cap / current price",
                date_or_period="Latest Yahoo market snapshot",
                kind="computed_market_cap",
                formula="marketCap / currentPrice",
            )
        )

    if not candidates:
        return ShareCountResolution(
            selected_shares=None,
            selected_shares_source=None,
            selected_shares_date_or_period=None,
            implied_shares_from_market_cap=implied_shares,
            selected_vs_implied_pct_diff=None,
            candidates=[],
            warnings=["Shares outstanding unavailable; per-share valuation disabled."],
            data_quality_risk=True,
        )

    if len(candidates) > 1:
        values = [candidate.value for candidate in candidates]
        min_value = min(values)
        max_value = max(values)
        if min_value > 0 and max_value / min_value >= DOUBLE_HALVE_THRESHOLD:
            warnings.append(
                "Share-count candidates differ by at least 2x; per-share valuation is highly sensitive to source choice."
            )

    for index, left in enumerate(candidates):
        for right in candidates[index + 1:]:
            diff = _pct_diff(left.value, right.value)
            if diff is not None and diff > MISMATCH_WARNING_THRESHOLD:
                warnings.append(
                    f"{left.source} differs from {right.source} by {diff:.1%}."
                )

    def score(candidate: ShareCountCandidate) -> tuple[float, int]:
        base = _candidate_priority(candidate)
        implied_diff = _pct_diff(candidate.value, implied_shares)
        penalty = 0.0
        age = _age_days(candidate.date_or_period)
        if candidate.kind == "filing_diluted" and age is not None and age > STALE_FILING_SHARE_DAYS:
            penalty += 4.0
        if implied_diff is not None:
            if implied_diff > MISMATCH_RISK_THRESHOLD:
                penalty += 10.0
            elif implied_diff > MISMATCH_WARNING_THRESHOLD:
                penalty += 2.0
        return base + penalty, base

    selected = min(candidates, key=score)
    selected_vs_implied = _pct_diff(selected.value, implied_shares)
    data_quality_risk = False

    if selected_vs_implied is not None and selected_vs_implied > MISMATCH_WARNING_THRESHOLD:
        warnings.append(
            f"Selected share count differs from market-cap-implied shares by {selected_vs_implied:.1%}."
        )
    if selected_vs_implied is not None and selected_vs_implied > MISMATCH_RISK_THRESHOLD:
        warnings.append(
            "Selected share count differs from market-cap-implied shares by more than 25%; mark valuation as data-quality risk."
        )
        data_quality_risk = True

    if selected.kind == "computed_market_cap":
        warnings.append(
            "Using market-cap-implied shares because direct share-count fields were missing or materially inconsistent."
        )
        data_quality_risk = True

    for candidate in candidates:
        age = _age_days(candidate.date_or_period)
        if candidate.kind == "filing_diluted" and age is not None and age > STALE_FILING_SHARE_DAYS:
            warnings.append(
                f"{candidate.source} is {age} days old; current Yahoo or market-cap-implied share counts may better reflect recent buybacks or dilution."
            )

    deduped_warnings = list(dict.fromkeys(warnings))
    return ShareCountResolution(
        selected_shares=selected.value,
        selected_shares_source=selected.source,
        selected_shares_date_or_period=selected.date_or_period,
        implied_shares_from_market_cap=implied_shares,
        selected_vs_implied_pct_diff=selected_vs_implied,
        candidates=candidates,
        warnings=deduped_warnings,
        data_quality_risk=data_quality_risk,
    )
