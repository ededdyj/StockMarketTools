"""Utility helpers for extracting key balance-sheet fundamentals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from models.share_count import ShareCountResolution, resolve_share_count


BALANCE_SHEET_CASH_FIELDS = [
    "Cash And Cash Equivalents",
    "Cash",
    "CashAndCashEquivalents",
]

BALANCE_SHEET_TOTAL_DEBT_FIELDS = [
    "Total Debt",
]

BALANCE_SHEET_NET_DEBT_FIELDS = [
    "Net Debt",
]

SHORT_TERM_DEBT_FIELDS = [
    "Short Long Term Debt",
    "Short Term Debt",
    "Current Debt",
]

LONG_TERM_DEBT_FIELDS = [
    "Long Term Debt",
]


@dataclass
class FundamentalsSnapshot:
    """Normalized view of cash, debt, shares, and metadata."""

    cash_and_equivalents: Optional[float] = None
    short_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    shares_outstanding: Optional[float] = None
    balance_sheet_as_of: Optional[str] = None
    pulled_at: str = ""
    cash_source: Optional[str] = None
    debt_source: Optional[str] = None
    shares_source: Optional[str] = None
    shares_date_or_period: Optional[str] = None
    implied_shares_from_market_cap: Optional[float] = None
    share_resolution: Optional[ShareCountResolution] = None
    warnings: List[str] = field(default_factory=list)
    note_tags: List[str] = field(default_factory=list)


def _latest_column_info(balance_sheet: Optional[pd.DataFrame]) -> Tuple[Optional[str], Optional[str]]:
    if balance_sheet is None or balance_sheet.empty:
        return None, None

    columns = list(balance_sheet.columns)
    if not columns:
        return None, None

    parsed = pd.to_datetime(columns, errors="coerce")
    parsed_series = pd.Series(parsed)
    if parsed_series.notna().any():
        latest_idx = parsed_series.idxmax()
        as_of_dt = parsed_series.iloc[latest_idx]
    else:
        latest_idx = 0
        as_of_dt = None

    column_label = columns[latest_idx]
    if isinstance(as_of_dt, pd.Timestamp):
        as_of_str = as_of_dt.strftime("%Y-%m-%d")
    else:
        as_of_str = str(column_label)
    return column_label, as_of_str


def _value_from_column(frame: Optional[pd.DataFrame], label: str, column_label: Optional[str]) -> Optional[float]:
    if frame is None or frame.empty or column_label is None:
        return None
    if label not in frame.index or column_label not in frame.columns:
        return None
    value = frame.at[label, column_label]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_cash(balance_sheet: Optional[pd.DataFrame], column_label: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    for field in BALANCE_SHEET_CASH_FIELDS:
        value = _value_from_column(balance_sheet, field, column_label)
        if value is not None:
            return value, field
    return None, None


def _resolve_debt_components(
    balance_sheet: Optional[pd.DataFrame],
    column_label: Optional[str],
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[str]]:
    for field in BALANCE_SHEET_TOTAL_DEBT_FIELDS:
        value = _value_from_column(balance_sheet, field, column_label)
        if value is not None:
            return None, None, value, field

    long_term = None
    for field in LONG_TERM_DEBT_FIELDS:
        candidate = _value_from_column(balance_sheet, field, column_label)
        if candidate is not None:
            long_term = candidate
            break

    short_term = None
    for field in SHORT_TERM_DEBT_FIELDS:
        candidate = _value_from_column(balance_sheet, field, column_label)
        if candidate is not None:
            short_term = candidate
            break

    if long_term is None and short_term is None:
        return None, None, None, None

    long_term = long_term or 0
    short_term = short_term or 0
    return short_term, long_term, long_term + short_term, "Long Term Debt + Short Term Debt"


def _resolve_net_debt(balance_sheet: Optional[pd.DataFrame], column_label: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    for field in BALANCE_SHEET_NET_DEBT_FIELDS:
        value = _value_from_column(balance_sheet, field, column_label)
        if value is not None:
            return value, field
    return None, None


def extract_fundamentals(
    info: Dict,
    balance_sheet: Optional[pd.DataFrame],
    financials: Optional[pd.DataFrame] = None,
) -> FundamentalsSnapshot:
    """Return normalized cash, debt, and share counts from Yahoo data."""

    warnings: List[str] = []
    latest_column, balance_sheet_as_of = _latest_column_info(balance_sheet)
    cash, cash_source = _resolve_cash(balance_sheet, latest_column)
    short_term_debt, long_term_debt, total_debt, debt_source = _resolve_debt_components(balance_sheet, latest_column)
    direct_net_debt, net_debt_source = _resolve_net_debt(balance_sheet, latest_column)

    if cash is None:
        warnings.append("Cash & equivalents missing; assuming 0.")
        cash = 0.0
        cash_source = None

    if total_debt is None and direct_net_debt is None:
        warnings.append("Total debt missing; assuming 0.")
        total_debt = 0.0
        debt_source = None

    if total_debt is not None:
        net_debt = total_debt - cash
    else:
        net_debt = direct_net_debt
        debt_source = net_debt_source
        total_debt = direct_net_debt + cash if direct_net_debt is not None and cash is not None else None

    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    share_resolution = resolve_share_count(
        info,
        balance_sheet=balance_sheet,
        financials=financials,
        current_price=current_price,
        market_cap=info.get("marketCap"),
    )
    shares = share_resolution.selected_shares
    shares_source = share_resolution.selected_shares_source
    shares_date_or_period = share_resolution.selected_shares_date_or_period
    if share_resolution.warnings:
        warnings.extend(share_resolution.warnings)
    if not shares or shares <= 0:
        shares = None
        warnings.append("Shares outstanding unavailable; per-share valuation disabled.")
        shares_source = None

    if balance_sheet is None or balance_sheet.empty:
        warnings.append("Balance sheet unavailable; debt and cash taken as 0.")
        balance_sheet_as_of = None

    pulled_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    note_tags: List[str] = []
    if shares is None:
        note_tags.append("MISSING_SHARES")
    if share_resolution.data_quality_risk:
        note_tags.append("SHARE_COUNT_RISK")
    if cash_source is None:
        note_tags.append("ASSUMED_CASH_ZERO")
    if debt_source is None:
        note_tags.append("ASSUMED_DEBT_ZERO")
    if balance_sheet_as_of is None:
        note_tags.append("NO_BALANCE_SHEET")
    if net_debt is not None and net_debt < 0:
        note_tags.append("NET_CASH")

    note_tags = sorted(set(note_tags))

    return FundamentalsSnapshot(
        cash_and_equivalents=cash,
        short_term_debt=short_term_debt,
        long_term_debt=long_term_debt,
        total_debt=total_debt,
        net_debt=net_debt,
        shares_outstanding=shares,
        balance_sheet_as_of=balance_sheet_as_of,
        pulled_at=pulled_at,
        cash_source=cash_source,
        debt_source=debt_source,
        shares_source=shares_source,
        shares_date_or_period=shares_date_or_period,
        implied_shares_from_market_cap=share_resolution.implied_shares_from_market_cap,
        share_resolution=share_resolution,
        warnings=warnings,
        note_tags=note_tags,
    )
