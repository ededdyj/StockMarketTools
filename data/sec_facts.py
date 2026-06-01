"""SEC EDGAR companyfacts adapter for financial health statement fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from typing import Optional

import pandas as pd
import requests

from models.financial_health import calculate_financial_health
from models.free_cash_flow import FreeCashFlowSnapshot, snapshot_from_sec_companyfacts


SEC_BASE_URL = "https://data.sec.gov"
SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_SEC_USER_AGENT = "StockMarketTools ededdyj@users.noreply.github.com"
SEC_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
STATIC_TICKER_CIKS = {
    "AAPL": "0000320193",
    "AMAT": "0000006951",
    "AMZN": "0001018724",
    "DELL": "0001571996",
    "GOOG": "0001652044",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "TSLA": "0001318605",
}


@dataclass(frozen=True)
class SecFinancialStatements:
    financials: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    cik: Optional[str] = None
    source_note: str = "Yahoo Finance"
    warnings: list[str] = field(default_factory=list)


INCOME_CONCEPTS = {
    "Net Income": ["NetIncomeLoss", "ProfitLoss"],
    "Total Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "Gross Profit": ["GrossProfit"],
}

BALANCE_CONCEPTS = {
    "Total Assets": ["Assets"],
    "Long Term Debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ],
    "Current Assets": ["AssetsCurrent"],
    "Current Liabilities": ["LiabilitiesCurrent"],
    "Ordinary Shares Number": [
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
        "CommonStocksIncludingAdditionalPaidInCapitalSharesOutstanding",
    ],
}

CASHFLOW_CONCEPTS = {
    "Operating Cash Flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "Capital Expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForProceedsFromProductiveAssets",
    ],
}


def _request_json(url: str) -> dict:
    response = requests.get(url, headers=sec_headers(), timeout=20)
    response.raise_for_status()
    return response.json()


def sec_headers() -> dict[str, str]:
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", DEFAULT_SEC_USER_AGENT)
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


@lru_cache(maxsize=1)
def _ticker_to_cik_map() -> dict[str, str]:
    payload = _request_json(SEC_TICKER_URL)
    mapping = {}
    for item in payload.values():
        ticker = str(item.get("ticker", "")).upper()
        cik = item.get("cik_str")
        if ticker and cik:
            mapping[ticker] = str(cik).zfill(10)
    return mapping


def ticker_to_cik(ticker: str) -> Optional[str]:
    normalized = ticker.upper().replace(".", "-")
    if normalized in STATIC_TICKER_CIKS:
        return STATIC_TICKER_CIKS[normalized]
    return _ticker_to_cik_map().get(normalized)


def _units_for_fact(fact: dict, preferred_units: tuple[str, ...]) -> list[dict]:
    units = fact.get("units", {})
    for unit in preferred_units:
        if unit in units:
            return units[unit]
    for unit_values in units.values():
        return unit_values
    return []


def _annual_series(companyfacts: dict, tag: str, preferred_units: tuple[str, ...]) -> pd.Series:
    fact = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not fact:
        return pd.Series(dtype=float)

    rows = []
    for item in _units_for_fact(fact, preferred_units):
        if item.get("form") not in SEC_FORMS or item.get("fp") != "FY":
            continue
        end = item.get("end")
        value = item.get("val")
        if end is None or value is None:
            continue
        rows.append(
            {
                "end": end,
                "filed": item.get("filed", ""),
                "fy": item.get("fy", 0),
                "value": value,
            }
        )

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows)
    df["end"] = pd.to_datetime(df["end"], errors="coerce")
    df = df.dropna(subset=["end"]).sort_values(["end", "filed"])
    df = df.drop_duplicates(subset=["end"], keep="last")
    series = pd.Series(df["value"].astype(float).values, index=df["end"].dt.strftime("%Y-%m-%d"))
    return series.sort_index(ascending=False)


def _series_for_label(companyfacts: dict, tags: list[str], preferred_units: tuple[str, ...]) -> pd.Series:
    for tag in tags:
        series = _annual_series(companyfacts, tag, preferred_units)
        if not series.empty:
            return series
    return pd.Series(dtype=float)


def _statement_frame(companyfacts: dict, concepts: dict[str, list[str]], preferred_units: tuple[str, ...]) -> pd.DataFrame:
    rows = {}
    for label, tags in concepts.items():
        series = _series_for_label(companyfacts, tags, preferred_units)
        if not series.empty:
            rows[label] = series
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame.from_dict(rows, orient="index")
    parsed_columns = pd.to_datetime(frame.columns, errors="coerce")
    if parsed_columns.notna().any():
        order = pd.Series(parsed_columns, index=frame.columns).sort_values(ascending=False).index
        frame = frame.loc[:, order]
    return frame


def statements_from_companyfacts(companyfacts: dict, cik: Optional[str] = None) -> SecFinancialStatements:
    financials = _statement_frame(companyfacts, INCOME_CONCEPTS, ("USD",))
    balance_sheet = _statement_frame(companyfacts, BALANCE_CONCEPTS, ("USD", "shares"))
    cashflow = _statement_frame(companyfacts, CASHFLOW_CONCEPTS, ("USD",))
    warnings = []
    if financials.empty and balance_sheet.empty and cashflow.empty:
        warnings.append("SEC EDGAR companyfacts returned no usable financial health fields.")
    return SecFinancialStatements(
        financials=financials,
        balance_sheet=balance_sheet,
        cashflow=cashflow,
        cik=cik,
        source_note=f"Yahoo Finance with SEC EDGAR fallback (CIK {cik})" if cik else "Yahoo Finance with SEC EDGAR fallback",
        warnings=warnings,
    )


@lru_cache(maxsize=512)
def get_sec_financial_health_statements(ticker: str) -> SecFinancialStatements:
    try:
        cik = ticker_to_cik(ticker)
        if not cik:
            return SecFinancialStatements(warnings=[f"No SEC CIK found for {ticker}."])
        payload = _request_json(f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json")
        return statements_from_companyfacts(payload, cik=cik)
    except Exception as exc:
        return SecFinancialStatements(warnings=[f"SEC EDGAR fallback failed for {ticker}: {exc}"])


@lru_cache(maxsize=512)
def get_sec_free_cash_flow_snapshot(ticker: str) -> tuple[Optional[FreeCashFlowSnapshot], list[str]]:
    """Return the best SEC Companyfacts FCF snapshot available for a ticker."""

    try:
        cik = ticker_to_cik(ticker)
        if not cik:
            return None, [f"No SEC CIK found for {ticker}."]
        payload = _request_json(f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json")
        snapshot = snapshot_from_sec_companyfacts(payload, cik=cik)
        if snapshot is None:
            return None, [f"SEC EDGAR companyfacts did not include enough cash-flow fields for {ticker}."]
        return snapshot, []
    except Exception as exc:
        return None, [f"SEC EDGAR FCF lookup failed for {ticker}: {exc}"]


def merge_statement_frame(primary: Optional[pd.DataFrame], fallback: Optional[pd.DataFrame]) -> pd.DataFrame:
    primary = _normalize_statement_columns(primary if primary is not None else pd.DataFrame())
    fallback = _normalize_statement_columns(fallback if fallback is not None else pd.DataFrame())
    if primary.empty:
        merged = fallback.copy()
    elif fallback.empty:
        merged = primary.copy()
    else:
        merged = primary.combine_first(fallback)

    if merged.empty:
        return merged

    parsed_columns = pd.to_datetime(merged.columns, errors="coerce")
    if parsed_columns.notna().any():
        order = pd.Series(parsed_columns, index=merged.columns).sort_values(ascending=False).index
        merged = merged.loc[:, order]
    return merged


def _normalize_statement_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    normalized = frame.copy()
    parsed_columns = pd.to_datetime(normalized.columns, errors="coerce")
    if parsed_columns.notna().any():
        normalized.columns = [
            parsed.strftime("%Y-%m-%d") if not pd.isna(parsed) else str(column)
            for column, parsed in zip(normalized.columns, parsed_columns)
        ]
        normalized = normalized.T.groupby(level=0).first().T
    return normalized


def add_sec_fallback_to_statements(
    ticker: str,
    financials: Optional[pd.DataFrame],
    balance_sheet: Optional[pd.DataFrame],
    cashflow: Optional[pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str, list[str]]:
    yahoo_health = calculate_financial_health(financials, balance_sheet, cashflow)
    if yahoo_health.available_signals == yahoo_health.max_score:
        return (
            merge_statement_frame(financials, None),
            merge_statement_frame(balance_sheet, None),
            merge_statement_frame(cashflow, None),
            "Yahoo Finance",
            [],
        )

    sec_statements = get_sec_financial_health_statements(ticker)
    merged_financials = merge_statement_frame(financials, sec_statements.financials)
    merged_balance_sheet = merge_statement_frame(balance_sheet, sec_statements.balance_sheet)
    merged_cashflow = merge_statement_frame(cashflow, sec_statements.cashflow)

    source_note = "Yahoo Finance"
    sec_used = not sec_statements.financials.empty or not sec_statements.balance_sheet.empty or not sec_statements.cashflow.empty
    if sec_used:
        source_note = sec_statements.source_note

    return (
        merged_financials,
        merged_balance_sheet,
        merged_cashflow,
        source_note,
        sec_statements.warnings if sec_used else [],
    )
