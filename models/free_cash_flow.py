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
TTM_METHODS = {"best_available", "ttm"}


@dataclass(frozen=True)
class FreeCashFlowSnapshot:
    value: Optional[float]
    source: str
    period: Optional[str]
    formula: str
    operating_cash_flow: Optional[float] = None
    capital_expenditures: Optional[float] = None
    method: str = "latest_fiscal_year"
    confidence_level: str = "Medium"
    warnings: list[str] = field(default_factory=list)
    yearly_values: list[tuple[str, float]] = field(default_factory=list)


def _ordered_columns(frame: Optional[pd.DataFrame]) -> list:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    columns = list(frame.columns)
    parsed = pd.to_datetime(columns, errors="coerce")
    parsed_series = pd.Series(parsed)
    if parsed_series.notna().any():
        return list(parsed_series.sort_values(ascending=False, na_position="last").index.map(lambda i: columns[i]))
    return columns


def _value(frame: Optional[pd.DataFrame], labels: list[str], column) -> Optional[float]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column is None:
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


def _resolved_fcf_for_column(cashflow: Optional[pd.DataFrame], column) -> tuple[Optional[float], Optional[float], Optional[float], str, str]:
    computed_fcf, operating_cash_flow, capex = _computed_fcf_for_column(cashflow, column)
    if computed_fcf is not None:
        return (
            computed_fcf,
            operating_cash_flow,
            capex,
            "operating cash flow and capital expenditures",
            "Free cash flow = operating cash flow - abs(capital expenditures)",
        )
    direct_fcf = _value(cashflow, FREE_CASH_FLOW_LABELS, column)
    if direct_fcf is not None:
        return (
            direct_fcf,
            operating_cash_flow,
            capex,
            "Free Cash Flow line item",
            "Free Cash Flow line item from provider cash-flow statement",
        )
    return None, operating_cash_flow, capex, "Unavailable", "Free cash flow = operating cash flow - capital expenditures"


def _latest_snapshot_from_frame(
    cashflow: Optional[pd.DataFrame],
    source_prefix: str,
    method: str,
    confidence_level: str,
) -> Optional[FreeCashFlowSnapshot]:
    columns = _ordered_columns(cashflow)
    if not columns:
        return None
    yearly_values: list[tuple[str, float]] = []
    latest_snapshot: Optional[FreeCashFlowSnapshot] = None
    for column in columns:
        computed_fcf, operating_cash_flow, capex, source_detail, formula = _resolved_fcf_for_column(cashflow, column)
        if computed_fcf is None:
            continue
        period = str(column)
        yearly_values.append((period, float(computed_fcf)))
        if latest_snapshot is None:
            latest_snapshot = FreeCashFlowSnapshot(
                value=float(computed_fcf),
                source=f"{source_prefix} {source_detail}",
                period=period,
                formula=formula,
                operating_cash_flow=operating_cash_flow,
                capital_expenditures=capex,
                method=method,
                confidence_level=confidence_level,
                yearly_values=yearly_values,
            )
    return latest_snapshot


def _ttm_snapshot_from_ttm_frame(cashflow: Optional[pd.DataFrame]) -> Optional[FreeCashFlowSnapshot]:
    snapshot = _latest_snapshot_from_frame(cashflow, "yfinance TTM", "ttm", "Medium")
    if snapshot is None:
        return None
    return FreeCashFlowSnapshot(
        value=snapshot.value,
        source=snapshot.source,
        period=snapshot.period,
        formula=snapshot.formula,
        operating_cash_flow=snapshot.operating_cash_flow,
        capital_expenditures=snapshot.capital_expenditures,
        method="ttm",
        confidence_level="Medium",
        yearly_values=snapshot.yearly_values,
    )


def _ttm_snapshot_from_quarterly_frame(cashflow: Optional[pd.DataFrame]) -> Optional[FreeCashFlowSnapshot]:
    columns = _ordered_columns(cashflow)
    if len(columns) < 4:
        return None

    quarter_values = []
    operating_cash_flow = 0.0
    capex_outflow = 0.0
    for column in columns[:4]:
        computed_fcf, ocf, capex, _, _ = _resolved_fcf_for_column(cashflow, column)
        if computed_fcf is None:
            return None
        quarter_values.append((str(column), float(computed_fcf)))
        if ocf is not None:
            operating_cash_flow += float(ocf)
        if capex is not None:
            capex_outflow += normalize_capex_as_outflow(capex)

    latest_period = str(columns[0])
    return FreeCashFlowSnapshot(
        value=sum(value for _, value in quarter_values),
        source="yfinance quarterly cashflow TTM",
        period=f"TTM through {latest_period}",
        formula="TTM free cash flow = sum of latest four quarterly FCF values; FCF = operating cash flow - abs(capital expenditures)",
        operating_cash_flow=operating_cash_flow,
        capital_expenditures=-capex_outflow,
        method="ttm",
        confidence_level="Medium",
        yearly_values=quarter_values,
    )


def resolve_free_cash_flow(
    cashflow: Optional[pd.DataFrame],
    method: str = "latest_fiscal_year",
    user_normalized_fcf: Optional[float] = None,
    quarterly_cashflow: Optional[pd.DataFrame] = None,
    ttm_cashflow: Optional[pd.DataFrame] = None,
    sec_fcf_snapshot: Optional[FreeCashFlowSnapshot] = None,
) -> FreeCashFlowSnapshot:
    """Resolve a DCF starting FCF with explicit source and formula metadata."""

    if user_normalized_fcf is not None:
        return FreeCashFlowSnapshot(
            value=float(user_normalized_fcf),
            source="User override",
            period="User entered",
            formula="User-entered normalized free cash flow",
            method="user_override",
            confidence_level="User supplied",
        )

    if method in TTM_METHODS:
        if sec_fcf_snapshot is not None and sec_fcf_snapshot.value is not None:
            return sec_fcf_snapshot
        ttm_snapshot = _ttm_snapshot_from_ttm_frame(ttm_cashflow)
        if ttm_snapshot is not None:
            return ttm_snapshot
        quarterly_snapshot = _ttm_snapshot_from_quarterly_frame(quarterly_cashflow)
        if quarterly_snapshot is not None:
            return quarterly_snapshot

    columns = _ordered_columns(cashflow)
    if not columns:
        return FreeCashFlowSnapshot(
            value=None,
            source="Unavailable",
            period=None,
            formula="Free cash flow = operating cash flow - capital expenditures",
            confidence_level="Low",
            warnings=["Cash flow statement unavailable; DCF starting FCF is missing."],
        )

    yearly_values: list[tuple[str, float]] = []
    latest_snapshot: Optional[FreeCashFlowSnapshot] = None
    for column in columns:
        computed_fcf, operating_cash_flow, capex, source_detail, formula = _resolved_fcf_for_column(cashflow, column)
        if computed_fcf is None:
            continue
        source = f"yfinance annual fallback {source_detail}"

        period = str(column)
        yearly_values.append((period, float(computed_fcf)))
        if latest_snapshot is None:
            warnings = []
            latest_quarterly_period = _ordered_columns(quarterly_cashflow)[:1]
            if latest_quarterly_period and str(latest_quarterly_period[0]) != period:
                warnings.append(
                    f"Annual FCF fallback uses {period}; newer quarterly cash-flow period {latest_quarterly_period[0]} exists but TTM FCF could not be built."
                )
            latest_snapshot = FreeCashFlowSnapshot(
                value=float(computed_fcf),
                source=source,
                period=period,
                formula=formula,
                operating_cash_flow=operating_cash_flow,
                capital_expenditures=capex,
                method="latest_fiscal_year",
                confidence_level="Low" if warnings else "Medium",
                warnings=warnings,
                yearly_values=yearly_values,
            )

    if not yearly_values:
        return FreeCashFlowSnapshot(
            value=None,
            source="Unavailable",
            period=None,
            formula="Free cash flow = operating cash flow - capital expenditures",
            confidence_level="Low",
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
            confidence_level="Medium",
            yearly_values=yearly_values,
        )

    if method in TTM_METHODS:
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
                confidence_level="Low",
                warnings=snapshot.warnings + ["Reliable SEC, quarterly, or TTM cash flow was not supplied; using latest fiscal-year FCF."],
                yearly_values=yearly_values,
            )

    return latest_snapshot or FreeCashFlowSnapshot(
        value=None,
        source="Unavailable",
        period=None,
        formula="Free cash flow = operating cash flow - capital expenditures",
        confidence_level="Low",
        warnings=["Free cash flow could not be resolved."],
    )


def snapshot_from_sec_companyfacts(companyfacts: dict, cik: Optional[str] = None) -> Optional[FreeCashFlowSnapshot]:
    """Build SEC TTM FCF from companyfacts annual and YTD 10-Q cash-flow facts."""

    ocf = _sec_fact_rows(
        companyfacts,
        [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
    )
    capex = _sec_fact_rows(
        companyfacts,
        [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsForProceedsFromProductiveAssets",
        ],
    )
    if ocf.empty or capex.empty:
        return None

    annual = _sec_joined_fcf(ocf, capex, annual=True)
    ytd = _sec_joined_fcf(ocf, capex, annual=False)
    if annual.empty:
        return None

    if not ytd.empty:
        latest_ytd = ytd.sort_values(["end", "filed"]).iloc[-1]
        prior_candidates = ytd[
            (ytd["fy"] == latest_ytd["fy"] - 1)
            & (ytd["fp"] == latest_ytd["fp"])
            & (ytd["end"] < latest_ytd["end"])
        ]
        annual_candidates = annual[annual["end"] < latest_ytd["end"]]
        if not prior_candidates.empty and not annual_candidates.empty:
            prior_ytd = prior_candidates.sort_values(["end", "filed"]).iloc[-1]
            latest_annual = annual_candidates.sort_values(["end", "filed"]).iloc[-1]
            ttm_fcf = latest_annual["fcf"] + latest_ytd["fcf"] - prior_ytd["fcf"]
            return FreeCashFlowSnapshot(
                value=float(ttm_fcf),
                source=f"SEC Companyfacts TTM (CIK {cik})" if cik else "SEC Companyfacts TTM",
                period=f"TTM through {latest_ytd['end'].strftime('%Y-%m-%d')}",
                formula="TTM FCF = latest annual FCF + current-year YTD FCF - prior-year same-period YTD FCF",
                operating_cash_flow=float(latest_annual["operating_cash_flow"] + latest_ytd["operating_cash_flow"] - prior_ytd["operating_cash_flow"]),
                capital_expenditures=-float(
                    latest_annual["capex_outflow"] + latest_ytd["capex_outflow"] - prior_ytd["capex_outflow"]
                ),
                method="ttm",
                confidence_level="High",
                yearly_values=[
                    (latest_annual["end"].strftime("%Y-%m-%d"), float(latest_annual["fcf"])),
                    (latest_ytd["end"].strftime("%Y-%m-%d"), float(latest_ytd["fcf"])),
                    (prior_ytd["end"].strftime("%Y-%m-%d"), float(prior_ytd["fcf"])),
                ],
            )

    latest_annual = annual.sort_values(["end", "filed"]).iloc[-1]
    return FreeCashFlowSnapshot(
        value=float(latest_annual["fcf"]),
        source=f"SEC Companyfacts annual fallback (CIK {cik})" if cik else "SEC Companyfacts annual fallback",
        period=latest_annual["end"].strftime("%Y-%m-%d"),
        formula="Free cash flow = operating cash flow - payments for property, plant, and equipment",
        operating_cash_flow=float(latest_annual["operating_cash_flow"]),
        capital_expenditures=-float(latest_annual["capex_outflow"]),
        method="latest_fiscal_year",
        confidence_level="High",
        warnings=["SEC Companyfacts quarterly/YTD data was incomplete; using latest annual filing FCF."],
        yearly_values=[(latest_annual["end"].strftime("%Y-%m-%d"), float(latest_annual["fcf"]))],
    )


def _sec_fact_rows(companyfacts: dict, tags: list[str]) -> pd.DataFrame:
    rows = []
    facts = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        fact = facts.get(tag)
        if not fact:
            continue
        for item in fact.get("units", {}).get("USD", []):
            if item.get("form") not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}:
                continue
            start = pd.to_datetime(item.get("start"), errors="coerce")
            end = pd.to_datetime(item.get("end"), errors="coerce")
            value = item.get("val")
            if pd.isna(start) or pd.isna(end) or value is None:
                continue
            days = (end - start).days
            rows.append(
                {
                    "start": start,
                    "end": end,
                    "filed": item.get("filed", ""),
                    "fy": int(item.get("fy") or end.year),
                    "fp": item.get("fp"),
                    "form": item.get("form"),
                    "days": days,
                    "value": float(value),
                }
            )
        if rows:
            break
    return pd.DataFrame(rows)


def _sec_joined_fcf(ocf: pd.DataFrame, capex: pd.DataFrame, annual: bool) -> pd.DataFrame:
    if annual:
        left = ocf[(ocf["fp"] == "FY") | (ocf["days"] >= 300)]
        right = capex[(capex["fp"] == "FY") | (capex["days"] >= 300)]
    else:
        left = ocf[(ocf["fp"].isin(["Q1", "Q2", "Q3"])) & (ocf["days"] < 300)]
        right = capex[(capex["fp"].isin(["Q1", "Q2", "Q3"])) & (capex["days"] < 300)]
    if left.empty or right.empty:
        return pd.DataFrame()
    joined = left.merge(
        right,
        on=["end", "fy", "fp"],
        suffixes=("_ocf", "_capex"),
    )
    if joined.empty:
        return joined
    joined["filed"] = joined[["filed_ocf", "filed_capex"]].max(axis=1)
    joined["operating_cash_flow"] = joined["value_ocf"]
    joined["capex_outflow"] = joined["value_capex"].abs()
    joined["fcf"] = joined["operating_cash_flow"] - joined["capex_outflow"]
    joined = joined.sort_values(["end", "filed"]).drop_duplicates(subset=["end", "fy", "fp"], keep="last")
    return joined
