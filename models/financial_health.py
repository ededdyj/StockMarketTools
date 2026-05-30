"""Financial health scoring based on Piotroski-style accounting signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class HealthSignal:
    category: str
    name: str
    formula: str
    passed: Optional[bool]
    points: int
    latest_value: Optional[float] = None
    previous_value: Optional[float] = None
    note: str = ""


@dataclass(frozen=True)
class FinancialHealthResult:
    score: int
    max_score: int
    available_signals: int
    signals: list[HealthSignal]
    warnings: list[str]

    @property
    def score_ratio(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0

    @property
    def available_score_ratio(self) -> Optional[float]:
        if not self.available_signals:
            return None
        return self.score / self.available_signals


INCOME_NET_INCOME_FIELDS = ["Net Income", "Net Income Common Stockholders"]
INCOME_REVENUE_FIELDS = ["Total Revenue", "Operating Revenue"]
INCOME_GROSS_PROFIT_FIELDS = ["Gross Profit"]

CASHFLOW_OPERATING_CF_FIELDS = ["Operating Cash Flow", "Total Cash From Operating Activities"]

BALANCE_TOTAL_ASSETS_FIELDS = ["Total Assets"]
BALANCE_LONG_TERM_DEBT_FIELDS = ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]
BALANCE_CURRENT_ASSETS_FIELDS = ["Current Assets", "Total Current Assets"]
BALANCE_CURRENT_LIABILITIES_FIELDS = ["Current Liabilities", "Total Current Liabilities"]
BALANCE_SHARES_FIELDS = ["Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"]


def _latest_two_columns(*frames: Optional[pd.DataFrame]) -> list:
    columns = []
    for frame in frames:
        if frame is not None and not frame.empty:
            columns.extend(list(frame.columns))

    if not columns:
        return []

    unique_columns = list(dict.fromkeys(columns))
    parsed = pd.to_datetime(unique_columns, errors="coerce")
    parsed_series = pd.Series(parsed)
    if parsed_series.notna().any():
        ordered_indices = parsed_series.sort_values(ascending=False, na_position="last").index
        return [unique_columns[i] for i in ordered_indices[:2]]
    return unique_columns[:2]


def _value(frame: Optional[pd.DataFrame], fields: list[str], column) -> Optional[float]:
    if frame is None or frame.empty or column is None:
        return None
    if column not in frame.columns:
        return None
    for field in fields:
        if field in frame.index:
            try:
                value = frame.at[field, column]
                if pd.isna(value):
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _signal(
    category: str,
    name: str,
    formula: str,
    passed: Optional[bool],
    latest_value: Optional[float] = None,
    previous_value: Optional[float] = None,
    note: str = "",
) -> HealthSignal:
    return HealthSignal(
        category=category,
        name=name,
        formula=formula,
        passed=passed,
        points=1 if passed else 0,
        latest_value=latest_value,
        previous_value=previous_value,
        note=note if passed is not None else note or "Missing required statement fields.",
    )


def _positive_signal(
    category: str,
    name: str,
    formula: str,
    value: Optional[float],
) -> HealthSignal:
    return _signal(category, name, formula, None if value is None else value > 0, latest_value=value)


def _improving_signal(
    category: str,
    name: str,
    formula: str,
    latest_value: Optional[float],
    previous_value: Optional[float],
    lower_is_better: bool = False,
) -> HealthSignal:
    if latest_value is None or previous_value is None:
        passed = None
    elif lower_is_better:
        passed = latest_value < previous_value
    else:
        passed = latest_value > previous_value
    return _signal(category, name, formula, passed, latest_value, previous_value)


def calculate_financial_health(
    income_statement: Optional[pd.DataFrame],
    balance_sheet: Optional[pd.DataFrame],
    cashflow: Optional[pd.DataFrame],
) -> FinancialHealthResult:
    """Return a transparent 0-9 financial health score.

    The model follows the structure of Piotroski's F-Score: four profitability
    checks, three leverage/liquidity/source-of-funds checks, and two operating
    efficiency checks. Missing inputs are marked N/A and disclosed separately.
    """

    latest_col, previous_col = (None, None)
    columns = _latest_two_columns(income_statement, balance_sheet, cashflow)
    if columns:
        latest_col = columns[0]
    if len(columns) > 1:
        previous_col = columns[1]

    latest_net_income = _value(income_statement, INCOME_NET_INCOME_FIELDS, latest_col)
    previous_net_income = _value(income_statement, INCOME_NET_INCOME_FIELDS, previous_col)
    latest_revenue = _value(income_statement, INCOME_REVENUE_FIELDS, latest_col)
    previous_revenue = _value(income_statement, INCOME_REVENUE_FIELDS, previous_col)
    latest_gross_profit = _value(income_statement, INCOME_GROSS_PROFIT_FIELDS, latest_col)
    previous_gross_profit = _value(income_statement, INCOME_GROSS_PROFIT_FIELDS, previous_col)

    latest_operating_cf = _value(cashflow, CASHFLOW_OPERATING_CF_FIELDS, latest_col)

    latest_assets = _value(balance_sheet, BALANCE_TOTAL_ASSETS_FIELDS, latest_col)
    previous_assets = _value(balance_sheet, BALANCE_TOTAL_ASSETS_FIELDS, previous_col)
    latest_long_term_debt = _value(balance_sheet, BALANCE_LONG_TERM_DEBT_FIELDS, latest_col)
    previous_long_term_debt = _value(balance_sheet, BALANCE_LONG_TERM_DEBT_FIELDS, previous_col)
    latest_current_assets = _value(balance_sheet, BALANCE_CURRENT_ASSETS_FIELDS, latest_col)
    previous_current_assets = _value(balance_sheet, BALANCE_CURRENT_ASSETS_FIELDS, previous_col)
    latest_current_liabilities = _value(balance_sheet, BALANCE_CURRENT_LIABILITIES_FIELDS, latest_col)
    previous_current_liabilities = _value(balance_sheet, BALANCE_CURRENT_LIABILITIES_FIELDS, previous_col)
    latest_shares = _value(balance_sheet, BALANCE_SHARES_FIELDS, latest_col)
    previous_shares = _value(balance_sheet, BALANCE_SHARES_FIELDS, previous_col)

    latest_roa = _ratio(latest_net_income, latest_assets)
    previous_roa = _ratio(previous_net_income, previous_assets)
    latest_leverage = _ratio(latest_long_term_debt, latest_assets)
    previous_leverage = _ratio(previous_long_term_debt, previous_assets)
    latest_current_ratio = _ratio(latest_current_assets, latest_current_liabilities)
    previous_current_ratio = _ratio(previous_current_assets, previous_current_liabilities)
    latest_gross_margin = _ratio(latest_gross_profit, latest_revenue)
    previous_gross_margin = _ratio(previous_gross_profit, previous_revenue)
    latest_asset_turnover = _ratio(latest_revenue, latest_assets)
    previous_asset_turnover = _ratio(previous_revenue, previous_assets)

    no_dilution = None
    if latest_shares is not None and previous_shares is not None:
        no_dilution = latest_shares <= previous_shares

    signals = [
        _positive_signal("Profitability", "Positive ROA", "Net Income / Total Assets > 0", latest_roa),
        _positive_signal("Profitability", "Positive Operating Cash Flow", "Operating Cash Flow > 0", latest_operating_cf),
        _improving_signal("Profitability", "ROA Improved", "Latest ROA > Previous ROA", latest_roa, previous_roa),
        _signal(
            "Profitability",
            "Cash Flow Beats Net Income",
            "Operating Cash Flow > Net Income",
            None if latest_operating_cf is None or latest_net_income is None else latest_operating_cf > latest_net_income,
            latest_operating_cf,
            latest_net_income,
            "Latest value is operating cash flow; comparison value is net income.",
        ),
        _improving_signal(
            "Leverage/Liquidity",
            "Long-Term Debt Ratio Decreased",
            "Long-Term Debt / Total Assets decreased",
            latest_leverage,
            previous_leverage,
            lower_is_better=True,
        ),
        _improving_signal(
            "Leverage/Liquidity",
            "Current Ratio Improved",
            "Current Assets / Current Liabilities improved",
            latest_current_ratio,
            previous_current_ratio,
        ),
        _signal(
            "Leverage/Liquidity",
            "No Share Dilution",
            "Latest shares outstanding <= previous shares outstanding",
            no_dilution,
            latest_shares,
            previous_shares,
        ),
        _improving_signal(
            "Operating Efficiency",
            "Gross Margin Improved",
            "Gross Profit / Total Revenue improved",
            latest_gross_margin,
            previous_gross_margin,
        ),
        _improving_signal(
            "Operating Efficiency",
            "Asset Turnover Improved",
            "Total Revenue / Total Assets improved",
            latest_asset_turnover,
            previous_asset_turnover,
        ),
    ]

    warnings = []
    if latest_col is None:
        warnings.append("No financial statement periods were available.")
    elif previous_col is None:
        warnings.append("Only one financial statement period was available; trend signals are unavailable.")

    missing_count = sum(signal.passed is None for signal in signals)
    if missing_count:
        warnings.append(f"{missing_count} of 9 financial health signals are unavailable from statement data.")

    return FinancialHealthResult(
        score=sum(signal.points for signal in signals),
        max_score=9,
        available_signals=sum(signal.passed is not None for signal in signals),
        signals=signals,
        warnings=warnings,
    )
