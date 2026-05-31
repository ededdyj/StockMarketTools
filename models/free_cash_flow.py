"""Free-cash-flow normalization helpers for DCF valuation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


OPERATING_CASH_FLOW_LABELS = [
    "Operating Cash Flow",
    "Total Cash From Operating Activities",
    "Net Cash Provided By Operating Activities",
]

CAPEX_LABELS = [
    "Capital Expenditure",
    "Capital Expenditures",
    "Capital Expenditure Reported",
]

FREE_CASH_FLOW_LABELS = ["Free Cash Flow"]


@dataclass(frozen=True)
class FreeCashFlowSnapshot:
    value: Optional[float]
    source: str
    period: Optional[str]
    formula: str
    operating_cash_flow: Optional[float] = None
    capital_expenditures: Optional[float] = None
    method: str = "latest_fiscal_year"
    warnings: list[str] = field(default_factory=list)
    yearly_values: list[tuple[str, float]] = field(default_factory=list)


def _ordered_columns(frame: Optional[pd.DataFrame]) -> list:
    if frame is None or frame.empty:
        return []
    columns = list(frame.columns)
    parsed = pd.to_datetime(columns, errors="coerce")
    parsed_series = pd.Series(parsed)
    if parsed_series.notna().any():
        return list(parsed_series.sort_values(ascending=False, na_position="last").index.map(lambda i: columns[i]))
    return columns


def _value(frame: Optional[pd.DataFrame], labels: list[str], column) -> Optional[float]:
    if frame is None or frame.empty or column is None:
        return None
    if column not in frame.columns:
        return None
    for label in labels:
        if label in frame.index:
            try:
                value = frame.at[label, column]
                if pd.isna(value):
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def normalize_capex_as_outflow(capex: Optional[float]) -> Optional[float]:
    """Return capex as a positive cash outflow regardless of source sign."""

    if capex is None:
        return None
    return abs(float(capex))


def calculate_free_cash_flow(operating_cash_flow: float, capital_expenditures: float) -> float:
    """Calculate FCF as OCF minus capex treated as a cash outflow."""

    return float(operating_cash_flow) - normalize_capex_as_outflow(capital_expenditures)


def _computed_fcf_for_column(cashflow: Optional[pd.DataFrame], column) -> tuple[Optional[float], Optional[float], Optional[float]]:
    operating_cash_flow = _value(cashflow, OPERATING_CASH_FLOW_LABELS, column)
    capex = _value(cashflow, CAPEX_LABELS, column)
    if operating_cash_flow is None or capex is None:
        return None, operating_cash_flow, capex
    return calculate_free_cash_flow(operating_cash_flow, capex), operating_cash_flow, capex


def resolve_free_cash_flow(
    cashflow: Optional[pd.DataFrame],
    method: str = "latest_fiscal_year",
    user_normalized_fcf: Optional[float] = None,
) -> FreeCashFlowSnapshot:
    """Resolve a DCF starting FCF with explicit source and formula metadata."""

    if user_normalized_fcf is not None:
        return FreeCashFlowSnapshot(
            value=float(user_normalized_fcf),
            source="User override",
            period="User entered",
            formula="User-entered normalized free cash flow",
            method="user_override",
        )

    columns = _ordered_columns(cashflow)
    if not columns:
        return FreeCashFlowSnapshot(
            value=None,
            source="Unavailable",
            period=None,
            formula="Free cash flow = operating cash flow - capital expenditures",
            warnings=["Cash flow statement unavailable; DCF starting FCF is missing."],
        )

    yearly_values: list[tuple[str, float]] = []
    latest_snapshot: Optional[FreeCashFlowSnapshot] = None
    for column in columns:
        computed_fcf, operating_cash_flow, capex = _computed_fcf_for_column(cashflow, column)
        if computed_fcf is None:
            direct_fcf = _value(cashflow, FREE_CASH_FLOW_LABELS, column)
            if direct_fcf is None:
                continue
            computed_fcf = direct_fcf
            source = "Yahoo Finance Free Cash Flow"
            formula = "Free Cash Flow line item from yfinance cashflow"
        else:
            source = "Yahoo Finance operating cash flow and capital expenditures"
            formula = "Free cash flow = operating cash flow - abs(capital expenditures)"

        period = str(column)
        yearly_values.append((period, float(computed_fcf)))
        if latest_snapshot is None:
            latest_snapshot = FreeCashFlowSnapshot(
                value=float(computed_fcf),
                source=source,
                period=period,
                formula=formula,
                operating_cash_flow=operating_cash_flow,
                capital_expenditures=capex,
                method="latest_fiscal_year",
                yearly_values=yearly_values,
            )

    if not yearly_values:
        return FreeCashFlowSnapshot(
            value=None,
            source="Unavailable",
            period=None,
            formula="Free cash flow = operating cash flow - capital expenditures",
            warnings=["Operating cash flow, capital expenditures, and Free Cash Flow line items are missing."],
        )

    if method == "three_year_average":
        values = [value for _, value in yearly_values[:3]]
        return FreeCashFlowSnapshot(
            value=sum(values) / len(values),
            source="Computed three-year average FCF",
            period=", ".join(period for period, _ in yearly_values[:3]),
            formula="Average of latest available annual free cash flow values",
            method="three_year_average",
            yearly_values=yearly_values,
        )

    if method == "ttm":
        snapshot = latest_snapshot
        if snapshot:
            return FreeCashFlowSnapshot(
                value=snapshot.value,
                source=snapshot.source,
                period=snapshot.period,
                formula=f"{snapshot.formula}; TTM unavailable from annual yfinance frame, using latest fiscal year",
                operating_cash_flow=snapshot.operating_cash_flow,
                capital_expenditures=snapshot.capital_expenditures,
                method="ttm",
                warnings=["Reliable quarterly/TTM cash flow was not supplied; using latest fiscal-year FCF."],
                yearly_values=yearly_values,
            )

    return latest_snapshot or FreeCashFlowSnapshot(
        value=None,
        source="Unavailable",
        period=None,
        formula="Free cash flow = operating cash flow - capital expenditures",
        warnings=["Free cash flow could not be resolved."],
    )
