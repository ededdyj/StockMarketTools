"""Dynamic DCF assumption estimates with transparent derivation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from data.market_inputs import MarketInputs
from models.valuation import DcfAssumptions


@dataclass(frozen=True)
class AssumptionLine:
    assumption: str
    value: float | int | str
    source: str
    formula: str
    note: str = ""


@dataclass(frozen=True)
class DynamicDcfEstimate:
    assumptions: DcfAssumptions
    lines: list[AssumptionLine]
    warnings: list[str]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _latest_value(frame: Optional[pd.DataFrame], labels: list[str]) -> Optional[float]:
    if frame is None or frame.empty:
        return None
    parsed = pd.to_datetime(frame.columns, errors="coerce")
    if parsed.notna().any():
        column = list(frame.columns)[pd.Series(parsed).idxmax()]
    else:
        column = frame.columns[0]
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


def _series(frame: Optional[pd.DataFrame], labels: list[str]) -> list[float]:
    if frame is None or frame.empty:
        return []
    for label in labels:
        if label in frame.index:
            values = []
            parsed = pd.to_datetime(frame.columns, errors="coerce")
            columns = list(frame.columns)
            if parsed.notna().any():
                order = pd.Series(parsed, index=columns).sort_values(ascending=False).index
            else:
                order = columns
            for column in order:
                try:
                    value = frame.at[label, column]
                    if not pd.isna(value):
                        values.append(float(value))
                except (TypeError, ValueError):
                    continue
            return values
    return []


def _median_growth(values: list[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    growth_rates = []
    for latest, previous in zip(values, values[1:]):
        if previous <= 0 or latest <= 0:
            continue
        growth_rates.append((latest / previous) - 1)
    if not growth_rates:
        return None
    return float(pd.Series(growth_rates).median())


def estimate_dynamic_dcf_assumptions(
    info: dict,
    financials: Optional[pd.DataFrame],
    balance_sheet: Optional[pd.DataFrame],
    cashflow: Optional[pd.DataFrame],
    market_inputs: MarketInputs,
) -> DynamicDcfEstimate:
    warnings = [*market_inputs.warnings]
    lines: list[AssumptionLine] = []

    beta = info.get("beta")
    if beta is None or pd.isna(beta):
        beta = 1.0
        beta_source = "Fallback beta"
        warnings.append("Beta missing; using market beta of 1.0.")
    else:
        beta = _clamp(float(beta), 0.6, 2.0)
        beta_source = "Yahoo Finance beta, clamped to 0.60-2.00"

    cost_of_equity = market_inputs.risk_free_rate + beta * market_inputs.equity_risk_premium

    market_cap = info.get("marketCap") or 0
    total_debt = _latest_value(balance_sheet, ["Total Debt", "Long Term Debt", "Long Term Debt And Capital Lease Obligation"]) or 0
    interest_expense = abs(_latest_value(financials, ["Interest Expense", "Interest Expense Non Operating"]) or 0)
    pretax_income = _latest_value(financials, ["Pretax Income", "Income Before Tax"])
    tax_expense = abs(_latest_value(financials, ["Tax Provision", "Income Tax Expense"]) or 0)

    if total_debt > 0 and interest_expense > 0:
        pretax_cost_of_debt = _clamp(interest_expense / total_debt, market_inputs.risk_free_rate, 0.15)
        debt_source = "Interest Expense / Total Debt, clamped"
    else:
        pretax_cost_of_debt = _clamp(market_inputs.risk_free_rate + 0.02, 0.03, 0.12)
        debt_source = "Risk-free rate + 2.00% fallback spread"

    if pretax_income and pretax_income > 0 and tax_expense > 0:
        tax_rate = _clamp(tax_expense / pretax_income, 0.0, 0.30)
        tax_source = "Tax Provision / Pretax Income, clamped"
    else:
        tax_rate = 0.21
        tax_source = "Fallback US statutory tax rate"

    after_tax_cost_of_debt = pretax_cost_of_debt * (1 - tax_rate)
    equity_weight = 1.0
    debt_weight = 0.0
    if market_cap and market_cap > 0 and total_debt > 0:
        equity_weight = market_cap / (market_cap + total_debt)
        debt_weight = total_debt / (market_cap + total_debt)

    discount_rate = equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt
    discount_rate = _clamp(discount_rate, 0.06, 0.16)

    fcf_growth = _median_growth(_series(cashflow, ["Free Cash Flow"]))
    revenue_growth = _median_growth(_series(financials, ["Total Revenue", "Operating Revenue"]))
    growth_candidates = [value for value in [fcf_growth, revenue_growth] if value is not None]
    if growth_candidates:
        growth_rate = sum(growth_candidates) / len(growth_candidates)
        growth_source = "Average of usable recent FCF and revenue growth"
    else:
        growth_rate = 0.03
        growth_source = "Fallback mature-company growth"
        warnings.append("No usable positive FCF/revenue growth history; using 3.00% growth fallback.")
    growth_rate = _clamp(growth_rate, 0.0, 0.12)

    terminal_growth_rate = min(market_inputs.risk_free_rate, 0.03, discount_rate - 0.01)
    terminal_growth_rate = _clamp(terminal_growth_rate, -0.02, 0.04)

    projection_years = 5

    lines.extend(
        [
            AssumptionLine("Risk-free rate", market_inputs.risk_free_rate, market_inputs.risk_free_source, "Latest long-term US Treasury proxy"),
            AssumptionLine("Equity risk premium", market_inputs.equity_risk_premium, market_inputs.equity_risk_premium_source, "Market-implied or fallback mature-market ERP"),
            AssumptionLine("Beta", beta, beta_source, "Company systematic risk input"),
            AssumptionLine("Cost of equity", cost_of_equity, "CAPM", "Risk-free rate + beta x equity risk premium"),
            AssumptionLine("Pretax cost of debt", pretax_cost_of_debt, debt_source, "Interest expense / debt, or risk-free + spread"),
            AssumptionLine("Tax rate", tax_rate, tax_source, "Tax provision / pretax income"),
            AssumptionLine("Equity weight", equity_weight, "Yahoo Finance market cap and latest debt", "Market cap / (market cap + debt)"),
            AssumptionLine("Debt weight", debt_weight, "Yahoo Finance market cap and latest debt", "Debt / (market cap + debt)"),
            AssumptionLine("Discount rate", discount_rate, "WACC estimate", "Equity weight x cost of equity + debt weight x after-tax cost of debt"),
            AssumptionLine("Growth rate", growth_rate, growth_source, "Recent growth blended and clamped to 0%-12%"),
            AssumptionLine("Terminal growth", terminal_growth_rate, "Conservative terminal cap", "min(risk-free rate, 3.00%, discount rate - 1.00%)"),
            AssumptionLine("Projection years", projection_years, "App default", "Five-year explicit forecast period"),
        ]
    )

    return DynamicDcfEstimate(
        assumptions=DcfAssumptions(
            discount_rate=discount_rate,
            growth_rate=growth_rate,
            terminal_growth_rate=terminal_growth_rate,
            projection_years=projection_years,
        ),
        lines=lines,
        warnings=warnings,
    )
