"""Valuation input provenance and freshness helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Optional

import pandas as pd

from data.market_inputs import MarketInputs
from models.dcf_assumptions import DynamicDcfEstimate
from models.free_cash_flow import FreeCashFlowSnapshot
from models.income_metrics import IncomeMetricsSnapshot
from utils.fundamentals import FundamentalsSnapshot


FRESHNESS_BUCKETS = [
    (45, "Fresh"),
    (120, "Recent"),
    (365, "Stale"),
]


@dataclass(frozen=True)
class ValuationInputProvenance:
    name: str
    value: object
    source: str
    formula: str
    period_or_as_of: Optional[str] = None
    retrieval_timestamp: Optional[str] = None
    confidence: str = "Medium"
    warning: Optional[str] = None
    category: str = "Derived estimate"
    age_days: Optional[int] = None
    freshness_label: str = "Unknown"


@dataclass(frozen=True)
class DataFreshnessReport:
    run_timestamp: str
    rows: list[ValuationInputProvenance]
    warnings: list[str] = field(default_factory=list)


def parse_date(value: Optional[str]) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if str(value).strip() == "":
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    if match:
        value = match.group(0)
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.tz_localize(None) if parsed.tzinfo else parsed
    return None


def age_in_days(value: Optional[str], now: Optional[pd.Timestamp] = None) -> Optional[int]:
    parsed = parse_date(value)
    if parsed is None:
        return None
    now = now or pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    return max((now - parsed).days, 0)


def freshness_label(age_days: Optional[int]) -> str:
    if age_days is None:
        return "Unknown"
    for max_days, label in FRESHNESS_BUCKETS:
        if age_days <= max_days:
            return label
    return "Very stale"


def _latest_statement_period(frame: Optional[pd.DataFrame]) -> Optional[str]:
    if frame is None or frame.empty:
        return None
    columns = list(frame.columns)
    parsed = pd.to_datetime(columns, errors="coerce")
    if parsed.notna().any():
        idx = pd.Series(parsed).idxmax()
        return pd.Timestamp(parsed[idx]).strftime("%Y-%m-%d")
    return str(columns[0]) if columns else None


def _dynamic_line(dynamic_estimate: Optional[DynamicDcfEstimate], name: str):
    if dynamic_estimate is None:
        return None
    for line in dynamic_estimate.lines:
        if line.assumption == name:
            return line
    return None


def _market_input_date(source: str) -> Optional[str]:
    if "(" not in source or ")" not in source:
        return None
    return source.rsplit("(", 1)[-1].split(")", 1)[0]


def _make_input(
    name: str,
    value: object,
    source: str,
    formula: str,
    period_or_as_of: Optional[str],
    retrieval_timestamp: str,
    confidence: str,
    category: str,
    warning: Optional[str] = None,
) -> ValuationInputProvenance:
    age = age_in_days(period_or_as_of)
    return ValuationInputProvenance(
        name=name,
        value=value,
        source=source,
        formula=formula,
        period_or_as_of=period_or_as_of,
        retrieval_timestamp=retrieval_timestamp,
        confidence=confidence,
        warning=warning,
        category=category,
        age_days=age,
        freshness_label=freshness_label(age),
    )


def build_valuation_input_provenance(
    info: dict,
    fundamentals: FundamentalsSnapshot,
    fcf_snapshot: FreeCashFlowSnapshot,
    dynamic_estimate: Optional[DynamicDcfEstimate],
    market_inputs: MarketInputs,
    financials: Optional[pd.DataFrame] = None,
    income_metrics: Optional[IncomeMetricsSnapshot] = None,
) -> DataFreshnessReport:
    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    income_period = _latest_statement_period(financials)
    pulled_at = fundamentals.pulled_at or run_timestamp
    price_period = run_timestamp

    rf_line = _dynamic_line(dynamic_estimate, "Risk-free rate")
    erp_line = _dynamic_line(dynamic_estimate, "Equity risk premium")
    discount_line = _dynamic_line(dynamic_estimate, "Discount rate")
    growth_line = _dynamic_line(dynamic_estimate, "Growth rate")
    terminal_line = _dynamic_line(dynamic_estimate, "Terminal growth")

    rows = [
        _make_input("Current Price", info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"), "Yahoo Finance market snapshot", "currentPrice / regularMarketPrice / previousClose", price_period, pulled_at, "Medium", "Market snapshot"),
        _make_input("Market Cap", info.get("marketCap"), "Yahoo Finance profile", "marketCap", price_period, pulled_at, "Medium", "Market snapshot"),
        _make_input("Shares Used", fundamentals.shares_outstanding, fundamentals.shares_source or "Unavailable", "Share-count resolver selected candidate", fundamentals.shares_date_or_period, pulled_at, "High" if "Filing-derived" in (fundamentals.shares_source or "") else "Medium", "Official filing data" if "Filing-derived" in (fundamentals.shares_source or "") else "Market snapshot"),
        _make_input("Implied Shares", fundamentals.implied_shares_from_market_cap, "Computed", "marketCap / currentPrice", price_period, pulled_at, "Medium", "Derived estimate"),
        _make_input("Cash", fundamentals.cash_and_equivalents, fundamentals.cash_source or "Fallback/missing", "Latest balance-sheet cash field", fundamentals.balance_sheet_as_of, pulled_at, "High" if fundamentals.cash_source else "Low", "Official filing data" if fundamentals.cash_source else "Fallback estimate", "Cash missing; assumed zero." if not fundamentals.cash_source else None),
        _make_input("Total Debt", fundamentals.total_debt, fundamentals.debt_source or "Fallback/missing", "Total Debt or Short + Long Debt", fundamentals.balance_sheet_as_of, pulled_at, "High" if fundamentals.debt_source else "Low", "Official filing data" if fundamentals.debt_source else "Fallback estimate", "Debt missing; assumed zero." if not fundamentals.debt_source else None),
        _make_input("Net Debt", fundamentals.net_debt, "Computed", "total debt - cash and equivalents", fundamentals.balance_sheet_as_of, pulled_at, "Medium", "Derived estimate"),
        _make_input("Operating Cash Flow", fcf_snapshot.operating_cash_flow, fcf_snapshot.source, "Cash flow statement operating cash flow", fcf_snapshot.period, pulled_at, fcf_snapshot.confidence_level if fcf_snapshot.operating_cash_flow is not None else "Low", "Official filing data" if "SEC" in fcf_snapshot.source else "Market snapshot" if fcf_snapshot.operating_cash_flow is not None else "Fallback estimate"),
        _make_input("Capital Expenditures", fcf_snapshot.capital_expenditures, fcf_snapshot.source, "Capex treated as cash outflow", fcf_snapshot.period, pulled_at, fcf_snapshot.confidence_level if fcf_snapshot.capital_expenditures is not None else "Low", "Official filing data" if "SEC" in fcf_snapshot.source else "Market snapshot" if fcf_snapshot.capital_expenditures is not None else "Fallback estimate"),
        _make_input("Free Cash Flow", fcf_snapshot.value, fcf_snapshot.source, fcf_snapshot.formula, fcf_snapshot.period, pulled_at, fcf_snapshot.confidence_level if fcf_snapshot.value is not None else "Low", "Official filing data" if "SEC" in fcf_snapshot.source else "Derived estimate" if fcf_snapshot.value is not None else "Fallback estimate"),
        _make_input("Revenue", income_metrics.revenue if income_metrics else info.get("totalRevenue"), income_metrics.source if income_metrics else "Yahoo Finance profile", "TTM quarterly revenue, annual revenue, or totalRevenue fallback", income_metrics.period if income_metrics else income_period, pulled_at, income_metrics.confidence_level if income_metrics else "Medium", "Derived estimate" if income_metrics and income_metrics.method == "ttm_quarterly" else "Market snapshot"),
        _make_input("Net Income", income_metrics.net_income if income_metrics else info.get("netIncomeToCommon"), income_metrics.source if income_metrics else "Yahoo Finance profile", "TTM quarterly net income, annual net income, or netIncomeToCommon fallback", income_metrics.period if income_metrics else income_period, pulled_at, income_metrics.confidence_level if income_metrics else "Medium", "Derived estimate" if income_metrics and income_metrics.method == "ttm_quarterly" else "Market snapshot"),
        _make_input("EPS", income_metrics.eps if income_metrics else info.get("trailingEps"), income_metrics.source if income_metrics else "Yahoo Finance profile", "TTM net income / shares used, reported EPS, or trailingEps fallback", income_metrics.period if income_metrics else income_period, pulled_at, income_metrics.confidence_level if income_metrics else "Medium", "Derived estimate" if income_metrics and income_metrics.method == "ttm_quarterly" else "Market snapshot"),
        _make_input("Beta", info.get("beta"), "Yahoo Finance profile", "beta", price_period, pulled_at, "Medium", "Market snapshot"),
        _make_input("Risk-free Rate", market_inputs.risk_free_rate, market_inputs.risk_free_source, "Latest long-term US Treasury proxy", _market_input_date(market_inputs.risk_free_source), pulled_at, "Medium", "Market snapshot"),
        _make_input("Equity Risk Premium", market_inputs.equity_risk_premium, market_inputs.equity_risk_premium_source, "Market-implied or fallback mature-market ERP", _market_input_date(market_inputs.equity_risk_premium_source), pulled_at, "Medium", "Market snapshot"),
        _make_input("Discount Rate / WACC", discount_line.value if discount_line else None, discount_line.source if discount_line else "Unavailable", discount_line.formula if discount_line else "WACC estimate", None, pulled_at, "Medium", "Derived estimate"),
        _make_input("Explicit FCF Growth", growth_line.value if growth_line else None, growth_line.source if growth_line else "Unavailable", growth_line.formula if growth_line else "Recent growth blend", None, pulled_at, "Medium", "Derived estimate"),
        _make_input("Terminal Growth", terminal_line.value if terminal_line else None, terminal_line.source if terminal_line else "Unavailable", terminal_line.formula if terminal_line else "Terminal growth cap", None, pulled_at, "Medium", "Derived estimate"),
    ]

    warnings = []
    if age_in_days(fcf_snapshot.period) is None:
        warnings.append("Cash-flow statement period could not be parsed.")
    elif age_in_days(fcf_snapshot.period) > 120:
        warnings.append(
            f"Current market data is being mixed with cash-flow data from {fcf_snapshot.period}, which is more than 120 days old."
        )
    if age_in_days(fundamentals.balance_sheet_as_of) is None:
        warnings.append("Balance-sheet date could not be parsed.")
    if income_period is None:
        warnings.append("Income-statement period could not be parsed.")

    return DataFreshnessReport(run_timestamp=run_timestamp, rows=rows, warnings=warnings)
