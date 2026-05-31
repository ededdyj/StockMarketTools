"""Centralized DCF data-quality and assumption warnings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from models.dcf_assumptions import DynamicDcfEstimate
from models.free_cash_flow import FreeCashFlowSnapshot
from models.valuation import DcfAssumptions
from utils.fundamentals import FundamentalsSnapshot


@dataclass(frozen=True)
class DcfWarning:
    severity: str
    category: str
    message: str


def _add(warnings: list[DcfWarning], severity: str, category: str, message: str) -> None:
    warnings.append(DcfWarning(severity, category, message))


def _latest_value(frame: Optional[pd.DataFrame], labels: list[str]) -> Optional[float]:
    if frame is None or frame.empty:
        return None
    columns = list(frame.columns)
    parsed = pd.to_datetime(columns, errors="coerce")
    if parsed.notna().any():
        column = columns[pd.Series(parsed).idxmax()]
    else:
        column = columns[0]
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


def _balance_sheet_stale(as_of: Optional[str], max_age_days: int = 550) -> bool:
    if not as_of:
        return False
    parsed = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(parsed):
        return False
    now = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    return (now - parsed.tz_localize(None)).days > max_age_days


def generate_dcf_warnings(
    info: dict,
    fundamentals: FundamentalsSnapshot,
    assumptions: DcfAssumptions,
    fcf_snapshot: Optional[FreeCashFlowSnapshot],
    dynamic_estimate: Optional[DynamicDcfEstimate] = None,
    financials: Optional[pd.DataFrame] = None,
    cashflow: Optional[pd.DataFrame] = None,
    sec_warnings: Optional[list[str]] = None,
    philosophy_name: str = "",
) -> list[DcfWarning]:
    warnings: list[DcfWarning] = []

    dividend_yield = info.get("dividendYield")
    if dividend_yield is not None and dividend_yield > 0.15:
        _add(warnings, "High", "Dividend", f"Dividend yield is {dividend_yield:.1%}, above the 15% data-quality threshold.")

    payout_ratio = info.get("payoutRatio")
    if payout_ratio is not None and payout_ratio > 1:
        _add(warnings, "Medium", "Dividend", f"Payout ratio is {payout_ratio:.1%}, above 100%.")

    price_to_book = info.get("priceToBook")
    book_value = info.get("bookValue")
    if (price_to_book is not None and price_to_book < 0) or (book_value is not None and book_value < 0):
        _add(warnings, "Medium", "Balance Sheet", "Book value or price/book is negative; book-based valuation ratios may be distorted.")

    share_resolution = fundamentals.share_resolution
    if share_resolution:
        for message in share_resolution.warnings:
            severity = "High" if "25%" in message or "2x" in message else "Medium"
            _add(warnings, severity, "Shares", message)

    if assumptions.growth_rate >= 0.119:
        _add(warnings, "Medium", "Assumptions", "Explicit FCF growth default is at or near the 12% clamp.")

    spread = assumptions.discount_rate - assumptions.terminal_growth_rate
    if spread < 0.02:
        _add(warnings, "High", "Assumptions", "Discount rate is less than terminal growth + 2%; terminal value is highly sensitive.")
    elif spread < 0.03:
        _add(warnings, "Medium", "Assumptions", "Terminal growth is close to discount rate; review terminal value sensitivity.")

    if _balance_sheet_stale(fundamentals.balance_sheet_as_of):
        _add(warnings, "Medium", "Freshness", f"Balance sheet date {fundamentals.balance_sheet_as_of} appears stale.")

    if "ASSUMED_CASH_ZERO" in fundamentals.note_tags:
        _add(warnings, "Medium", "Inputs", "Cash field missing; app assumed cash and equivalents are zero.")
    if "ASSUMED_DEBT_ZERO" in fundamentals.note_tags:
        _add(warnings, "Medium", "Inputs", "Debt field missing; app assumed total debt is zero.")

    if fcf_snapshot is None or fcf_snapshot.value is None:
        _add(warnings, "High", "FCF", "Free cash flow is missing; DCF per-share output should not be trusted.")
    elif fcf_snapshot.value <= 0:
        _add(warnings, "High", "FCF", f"Starting free cash flow is non-positive ({fcf_snapshot.value:,.0f}).")

    net_income = _latest_value(financials, ["Net Income", "Net Income Common Stockholders"])
    operating_cf = fcf_snapshot.operating_cash_flow if fcf_snapshot else _latest_value(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    if net_income and operating_cf is not None:
        gap = abs(operating_cf - net_income) / max(abs(net_income), 1.0)
        if gap > 0.50:
            _add(warnings, "Medium", "Quality", f"Operating cash flow differs from net income by {gap:.1%}; inspect accrual quality and working capital.")

    if financials is not None and not financials.empty:
        share_values = []
        for label in ["Diluted Average Shares", "Basic Average Shares"]:
            if label in financials.index:
                for value in financials.loc[label].dropna().head(2):
                    try:
                        share_values.append(float(value))
                    except (TypeError, ValueError):
                        continue
                break
        if len(share_values) >= 2 and share_values[1] > 0:
            share_change = abs(share_values[0] - share_values[1]) / share_values[1]
            if share_change > 0.10:
                _add(warnings, "Medium", "Shares", f"Major year-over-year share-count change detected ({share_change:.1%}).")

    if sec_warnings:
        for warning in sec_warnings:
            if "No SEC CIK" in warning or "failed" in warning:
                _add(warnings, "Low", "SEC", warning)

    if dynamic_estimate:
        for warning in dynamic_estimate.warnings:
            _add(warnings, "Low", "Dynamic Defaults", warning)

    if philosophy_name == "Long-term Value/DCF":
        _add(warnings, "Info", "Philosophy", "Value/DCF mode: prioritize FCF reliability, margin cyclicality, and terminal value sensitivity.")
    elif philosophy_name == "Dividend/Income":
        _add(warnings, "Info", "Philosophy", "Dividend mode: validate dividend yield, payout ratio, and payout sustainability against filings.")
    elif philosophy_name == "Growth-at-a-Reasonable-Price":
        _add(warnings, "Info", "Philosophy", "GARP mode: stress-test growth assumptions and valuation sensitivity.")
    elif philosophy_name == "Momentum/Trend":
        _add(warnings, "Info", "Philosophy", "Momentum mode: DCF is not a trading signal and can lag price action.")
    elif philosophy_name == "Index/Passive":
        _add(warnings, "Info", "Philosophy", "Index/passive mode: single-stock DCF is less relevant for ETFs and diversified funds.")

    unique = {}
    for warning in warnings:
        unique[(warning.severity, warning.category, warning.message)] = warning
    return list(unique.values())
