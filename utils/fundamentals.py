"""Utility helpers for extracting key balance-sheet fundamentals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


BALANCE_SHEET_CASH_FIELDS = [
    "Cash And Cash Equivalents",
    "Cash",
    "CashAndCashEquivalents",
]

BALANCE_SHEET_TOTAL_DEBT_FIELDS = [
    "Total Debt",
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

    cash_and_equivalents: Optional[float]
    total_debt: Optional[float]
    net_debt: Optional[float]
    shares_outstanding: Optional[float]
    balance_sheet_as_of: Optional[str]
    pulled_at: str
    cash_source: Optional[str] = None
    debt_source: Optional[str] = None
    shares_source: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def _first_column_value(frame: Optional[pd.DataFrame], label: str) -> Optional[float]:
    if frame is None or frame.empty:
        return None
    if label not in frame.index:
        return None
    series = frame.loc[label]
    if series.empty:
        return None
    value = series.iloc[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_cash(balance_sheet: Optional[pd.DataFrame]) -> tuple[Optional[float], Optional[str]]:
    for field in BALANCE_SHEET_CASH_FIELDS:
        value = _first_column_value(balance_sheet, field)
        if value is not None:
            return value, field
    return None, None


def _resolve_total_debt(balance_sheet: Optional[pd.DataFrame]) -> tuple[Optional[float], Optional[str]]:
    for field in BALANCE_SHEET_TOTAL_DEBT_FIELDS:
        value = _first_column_value(balance_sheet, field)
        if value is not None:
            return value, field

    long_term = None
    for field in LONG_TERM_DEBT_FIELDS:
        candidate = _first_column_value(balance_sheet, field)
        if candidate is not None:
            long_term = candidate
            break

    short_term = None
    for field in SHORT_TERM_DEBT_FIELDS:
        candidate = _first_column_value(balance_sheet, field)
        if candidate is not None:
            short_term = candidate
            break

    if long_term is None and short_term is None:
        return None, None

    long_term = long_term or 0
    short_term = short_term or 0
    return long_term + short_term, "Long Term Debt + Short Term Debt"


def extract_fundamentals(info: Dict, balance_sheet: Optional[pd.DataFrame]) -> FundamentalsSnapshot:
    """Return normalized cash, debt, and share counts from Yahoo data."""

    warnings: List[str] = []
    cash, cash_source = _resolve_cash(balance_sheet)
    total_debt, debt_source = _resolve_total_debt(balance_sheet)

    if cash is None:
        warnings.append("Cash & equivalents missing; assuming 0.")
        cash = 0.0
        cash_source = None

    if total_debt is None:
        warnings.append("Total debt missing; assuming 0.")
        total_debt = 0.0
        debt_source = None

    net_debt = None
    if total_debt is not None and cash is not None:
        net_debt = total_debt - cash

    shares_source = None
    shares = info.get("sharesOutstanding")
    if shares and shares > 0:
        shares_source = "sharesOutstanding"
    elif info.get("impliedSharesOutstanding"):
        shares = info["impliedSharesOutstanding"]
        shares_source = "impliedSharesOutstanding"
    if not shares or shares <= 0:
        shares = None
        warnings.append("Shares outstanding unavailable; per-share valuation disabled.")
        shares_source = None

    balance_sheet_as_of = None
    if balance_sheet is not None and not balance_sheet.empty:
        balance_sheet_as_of = str(balance_sheet.columns[0])
    else:
        warnings.append("Balance sheet unavailable; debt and cash taken as 0.")

    pulled_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    return FundamentalsSnapshot(
        cash_and_equivalents=cash,
        total_debt=total_debt,
        net_debt=net_debt,
        shares_outstanding=shares,
        balance_sheet_as_of=balance_sheet_as_of,
        pulled_at=pulled_at,
        cash_source=cash_source,
        debt_source=debt_source,
        shares_source=shares_source,
        warnings=warnings,
    )
