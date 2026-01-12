from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class ValuationResult:
    enterprise_value: Optional[float]
    equity_value: Optional[float]
    fair_value_per_share: Optional[float]


def _latest_period_column(frame) -> Optional[str]:
    if frame is None or frame.empty:
        return None
    columns = list(frame.columns)
    if not columns:
        return None
    parsed = pd.to_datetime(columns, errors="coerce")
    parsed_series = pd.Series(parsed)
    if parsed_series.notna().any():
        latest_idx = parsed_series.idxmax()
    else:
        latest_idx = 0
    return columns[latest_idx]


def _latest_free_cash_flow(cashflow_df):
    latest_column = _latest_period_column(cashflow_df)
    if latest_column is None:
        raise ValueError("Cash flow periods missing")
    return cashflow_df.loc['Free Cash Flow', latest_column]


def calculate_fair_value(
    cashflow_df,
    net_debt: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    discount_rate: float = 0.10,
    growth_rate: float = 0.03,
    terminal_growth_rate: float = 0.02,
    projection_years: int = 5,
) -> Optional[ValuationResult]:
    """Return enterprise/equity/per-share valuation details."""

    try:
        fcf = _latest_free_cash_flow(cashflow_df)
    except Exception as e:
        print("Error accessing Free Cash Flow data:", e)
        return None

    projected_fcf = [fcf * ((1 + growth_rate) ** i) for i in range(1, projection_years + 1)]
    terminal_value = projected_fcf[-1] * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
    pv_fcf = sum([cf / ((1 + discount_rate) ** i) for i, cf in enumerate(projected_fcf, start=1)])
    pv_terminal = terminal_value / ((1 + discount_rate) ** projection_years)
    enterprise_value = pv_fcf + pv_terminal

    equity_value = None
    if net_debt is not None:
        # Net debt is subtracted exactly once so that positive debt reduces
        # equity value and net cash (negative net debt) increases it.
        equity_value = enterprise_value - net_debt
    else:
        equity_value = enterprise_value

    fair_value_per_share = None
    if equity_value is not None and shares_outstanding:
        try:
            fair_value_per_share = equity_value / shares_outstanding
        except ZeroDivisionError:
            fair_value_per_share = None

    return ValuationResult(
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
    )


def calculate_fair_value_range(
    cashflow_df,
    net_debt: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    discount_rate_base=0.10,
    growth_rate_base=0.03,
    terminal_growth_rate=0.02,
    projection_years=5,
    discount_rate_variation=0.02,
    growth_rate_variation=0.01,
):
    """
    Calculate a confidence interval for the fair value per share by varying the discount and growth rates.

    Parameters:
      cashflow_df (DataFrame): Cash flow data.
      shares_outstanding (int): Number of shares outstanding.
      discount_rate_base (float): Base discount rate (default 10%).
      growth_rate_base (float): Base growth rate for free cash flow (default 3%).
      terminal_growth_rate (float): Terminal growth rate (default 2%).
      projection_years (int): Projection period (default 5 years).
      discount_rate_variation (float): Variation for discount rate (default ±2%).
      growth_rate_variation (float): Variation for growth rate (default ±1%).

    Returns:
      (min_fair_value, max_fair_value) tuple if calculations succeed, else None.
    """
    # Define the grid of assumption values
    discount_values = [discount_rate_base - discount_rate_variation, discount_rate_base,
                       discount_rate_base + discount_rate_variation]
    growth_values = [growth_rate_base - growth_rate_variation, growth_rate_base,
                     growth_rate_base + growth_rate_variation]

    fair_values = []
    for d in discount_values:
        for g in growth_values:
            result = calculate_fair_value(
                cashflow_df,
                net_debt=net_debt,
                shares_outstanding=shares_outstanding,
                discount_rate=d,
                growth_rate=g,
                terminal_growth_rate=terminal_growth_rate,
                projection_years=projection_years,
            )
            if result and result.fair_value_per_share is not None:
                fair_values.append(result.fair_value_per_share)

    if not fair_values:
        return None
    return min(fair_values), max(fair_values)
