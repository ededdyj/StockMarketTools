"""Income statement metric resolution for valuation provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


REVENUE_LABELS = ["Total Revenue", "Operating Revenue", "Revenue"]
NET_INCOME_LABELS = ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"]
EPS_LABELS = ["Diluted EPS", "Basic EPS"]


@dataclass(frozen=True)
class IncomeMetricsSnapshot:
    revenue: Optional[float]
    net_income: Optional[float]
    eps: Optional[float]
    source: str
    period: Optional[str]
    method: str
    confidence_level: str
    warnings: list[str] = field(default_factory=list)


def _ordered_columns(frame: Optional[pd.DataFrame]) -> list:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    columns = list(frame.columns)
    parsed = pd.to_datetime(columns, errors="coerce")
    if parsed.notna().any():
        return list(pd.Series(parsed, index=columns).sort_values(ascending=False).index)
    return columns


def _value(frame: Optional[pd.DataFrame], labels: list[str], column) -> Optional[float]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column is None:
        return None
    for label in labels:
        if label in frame.index and column in frame.columns:
            try:
                value = frame.at[label, column]
                if pd.isna(value):
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _sum_latest_four(frame: Optional[pd.DataFrame], labels: list[str]) -> tuple[Optional[float], Optional[str]]:
    columns = _ordered_columns(frame)
    if len(columns) < 4:
        return None, None
    values = []
    for column in columns[:4]:
        value = _value(frame, labels, column)
        if value is None:
            return None, None
        values.append(value)
    return sum(values), f"TTM through {columns[0]}"


def _latest_from_frame(frame: Optional[pd.DataFrame], labels: list[str]) -> tuple[Optional[float], Optional[str]]:
    columns = _ordered_columns(frame)
    if not columns:
        return None, None
    column = columns[0]
    return _value(frame, labels, column), str(column)


def resolve_income_metrics(
    info: dict,
    annual_financials: Optional[pd.DataFrame] = None,
    quarterly_financials: Optional[pd.DataFrame] = None,
    shares_outstanding: Optional[float] = None,
) -> IncomeMetricsSnapshot:
    """Prefer TTM quarterly income metrics before annual/profile fallbacks."""

    revenue, period = _sum_latest_four(quarterly_financials, REVENUE_LABELS)
    net_income, income_period = _sum_latest_four(quarterly_financials, NET_INCOME_LABELS)
    if revenue is not None or net_income is not None:
        period = period or income_period
        eps = None
        if net_income is not None and shares_outstanding:
            eps = net_income / shares_outstanding
        return IncomeMetricsSnapshot(
            revenue=revenue,
            net_income=net_income,
            eps=eps,
            source="yfinance quarterly financials TTM",
            period=period,
            method="ttm_quarterly",
            confidence_level="Medium",
            warnings=[] if eps is not None else ["EPS could not be derived because shares were unavailable."],
        )

    revenue, period = _latest_from_frame(annual_financials, REVENUE_LABELS)
    net_income, income_period = _latest_from_frame(annual_financials, NET_INCOME_LABELS)
    eps, eps_period = _latest_from_frame(annual_financials, EPS_LABELS)
    if eps is None and net_income is not None and shares_outstanding:
        eps = net_income / shares_outstanding
    if revenue is not None or net_income is not None or eps is not None:
        return IncomeMetricsSnapshot(
            revenue=revenue,
            net_income=net_income,
            eps=eps,
            source="yfinance annual financials fallback",
            period=period or income_period or eps_period,
            method="annual_fallback",
            confidence_level="Low",
            warnings=["Quarterly income statement data unavailable or incomplete; using annual financials."],
        )

    return IncomeMetricsSnapshot(
        revenue=info.get("totalRevenue"),
        net_income=info.get("netIncomeToCommon"),
        eps=info.get("trailingEps"),
        source="Yahoo Finance profile fallback",
        period=None,
        method="profile_fallback",
        confidence_level="Low",
        warnings=["Income statement data unavailable; using Yahoo profile fields."],
    )
