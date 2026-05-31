from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from models.free_cash_flow import FreeCashFlowSnapshot, resolve_free_cash_flow


@dataclass
class DcfAssumptions:
    discount_rate: float
    growth_rate: float
    terminal_growth_rate: float
    projection_years: int

    @classmethod
    def defaults(cls) -> "DcfAssumptions":
        return cls(0.10, 0.03, 0.02, 5)

    def validate(self) -> tuple[bool, Optional[str]]:
        errors = []
        if not (-0.5 <= self.discount_rate <= 0.5):
            errors.append("Discount rate must be between -50% and 50%.")
        if not (-0.5 <= self.growth_rate <= 0.5):
            errors.append("Growth rate must be between -50% and 50%.")
        if not (-0.5 <= self.terminal_growth_rate <= 0.5):
            errors.append("Terminal growth must be between -50% and 50%.")
        if not (1 <= self.projection_years <= 20):
            errors.append("Projection years must be between 1 and 20.")
        if self.discount_rate <= self.terminal_growth_rate:
            errors.append("Discount rate must be greater than terminal growth rate.")
        if errors:
            return False, " ".join(errors)
        return True, None


@dataclass
class ValuationResult:
    enterprise_value: Optional[float]
    equity_value: Optional[float]
    fair_value_per_share: Optional[float]
    starting_fcf: Optional[float] = None
    projected_fcf: list[float] = field(default_factory=list)
    terminal_value: Optional[float] = None
    pv_explicit_fcf: Optional[float] = None
    pv_terminal_value: Optional[float] = None
    net_debt: Optional[float] = None
    shares_used: Optional[float] = None
    fcf_snapshot: Optional[FreeCashFlowSnapshot] = None


@dataclass(frozen=True)
class ScenarioValuation:
    name: str
    assumptions: DcfAssumptions
    valuation: Optional[ValuationResult]
    upside_downside: Optional[float]
    thesis: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReverseDcfResult:
    implied_growth_rate: Optional[float]
    target_enterprise_value: Optional[float]
    target_equity_value: Optional[float]
    message: str
    valid: bool


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
    fcf = resolve_free_cash_flow(cashflow_df)
    if fcf.value is None:
        raise ValueError("Cash flow periods missing")
    return fcf.value


def _discounted_cash_flow_from_starting_fcf(
    starting_fcf: float,
    assumptions: DcfAssumptions,
    net_debt: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    fcf_snapshot: Optional[FreeCashFlowSnapshot] = None,
) -> Optional[ValuationResult]:
    discount_rate = assumptions.discount_rate
    growth_rate = assumptions.growth_rate
    terminal_growth_rate = assumptions.terminal_growth_rate
    projection_years = assumptions.projection_years

    valid, _ = assumptions.validate()
    if not valid:
        return None

    projected_fcf = [starting_fcf * ((1 + growth_rate) ** i) for i in range(1, projection_years + 1)]
    if not projected_fcf:
        return None
    terminal_value = projected_fcf[-1] * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
    pv_explicit_fcf = sum(cf / ((1 + discount_rate) ** i) for i, cf in enumerate(projected_fcf, start=1))
    pv_terminal_value = terminal_value / ((1 + discount_rate) ** projection_years)
    enterprise_value = pv_explicit_fcf + pv_terminal_value

    equity_value = enterprise_value - net_debt if net_debt is not None else enterprise_value
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
        starting_fcf=starting_fcf,
        projected_fcf=projected_fcf,
        terminal_value=terminal_value,
        pv_explicit_fcf=pv_explicit_fcf,
        pv_terminal_value=pv_terminal_value,
        net_debt=net_debt,
        shares_used=shares_outstanding,
        fcf_snapshot=fcf_snapshot,
    )


def calculate_fair_value(
    cashflow_df,
    net_debt: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    assumptions: Optional[DcfAssumptions] = None,
    starting_fcf: Optional[float] = None,
    discount_rate: float = 0.10,
    growth_rate: float = 0.03,
    terminal_growth_rate: float = 0.02,
    projection_years: int = 5,
) -> Optional[ValuationResult]:
    """Return enterprise/equity/per-share valuation details."""

    if assumptions is None:
        assumptions = DcfAssumptions(discount_rate, growth_rate, terminal_growth_rate, projection_years)
    discount_rate = assumptions.discount_rate
    growth_rate = assumptions.growth_rate
    terminal_growth_rate = assumptions.terminal_growth_rate
    projection_years = assumptions.projection_years

    fcf_snapshot = None
    if starting_fcf is None:
        fcf_snapshot = resolve_free_cash_flow(cashflow_df)
        if fcf_snapshot.value is None:
            print("Error accessing Free Cash Flow data:", "; ".join(fcf_snapshot.warnings))
            return None
        starting_fcf = fcf_snapshot.value

    return _discounted_cash_flow_from_starting_fcf(
        starting_fcf=float(starting_fcf),
        assumptions=assumptions,
        net_debt=net_debt,
        shares_outstanding=shares_outstanding,
        fcf_snapshot=fcf_snapshot,
    )


def calculate_fair_value_range(
    cashflow_df,
    net_debt: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    assumptions: Optional[DcfAssumptions] = None,
    starting_fcf: Optional[float] = None,
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
    if assumptions is None:
        assumptions = DcfAssumptions(discount_rate_base, growth_rate_base, terminal_growth_rate, projection_years)

    discount_values = [assumptions.discount_rate - discount_rate_variation,
                       assumptions.discount_rate,
                       assumptions.discount_rate + discount_rate_variation]
    growth_values = [assumptions.growth_rate - growth_rate_variation,
                     assumptions.growth_rate,
                     assumptions.growth_rate + growth_rate_variation]

    fair_values = []
    for d in discount_values:
        for g in growth_values:
            scenario_assumptions = DcfAssumptions(
                discount_rate=d,
                growth_rate=g,
                terminal_growth_rate=assumptions.terminal_growth_rate,
                projection_years=assumptions.projection_years,
            )
            result = calculate_fair_value(
                cashflow_df,
                net_debt=net_debt,
                shares_outstanding=shares_outstanding,
                assumptions=scenario_assumptions,
                starting_fcf=starting_fcf,
            )
            if result and result.fair_value_per_share is not None:
                fair_values.append(result.fair_value_per_share)

    if not fair_values:
        return None
    return min(fair_values), max(fair_values)


def calculate_scenario_valuations(
    starting_fcf: float,
    net_debt: Optional[float],
    shares_outstanding: Optional[float],
    current_price: Optional[float],
    scenarios: dict[str, DcfAssumptions],
) -> list[ScenarioValuation]:
    results = []
    for name, assumptions in scenarios.items():
        warnings = []
        valuation = _discounted_cash_flow_from_starting_fcf(
            starting_fcf=starting_fcf,
            assumptions=assumptions,
            net_debt=net_debt,
            shares_outstanding=shares_outstanding,
        )
        if valuation is None:
            warnings.append("Invalid scenario assumptions.")
        if assumptions.discount_rate - assumptions.terminal_growth_rate < 0.02:
            warnings.append("Terminal growth is too close to discount rate.")
        upside = None
        if valuation and valuation.fair_value_per_share is not None and current_price:
            upside = (valuation.fair_value_per_share - current_price) / current_price
        thesis_map = {
            "Bear": "FCF normalization/downcycle, lower margins, slower growth, higher discount rate.",
            "Base": "Management guidance partially achieved, moderate FCF conversion, stable terminal growth.",
            "Bull": "Sustained growth, strong FCF conversion, buybacks, durable margin structure.",
        }
        results.append(ScenarioValuation(name, assumptions, valuation, upside, thesis_map.get(name, ""), warnings))
    return results


def default_scenarios(base: DcfAssumptions) -> dict[str, DcfAssumptions]:
    return {
        "Bear": DcfAssumptions(
            discount_rate=base.discount_rate + 0.02,
            growth_rate=max(base.growth_rate - 0.03, -0.05),
            terminal_growth_rate=max(base.terminal_growth_rate - 0.01, -0.02),
            projection_years=base.projection_years,
        ),
        "Base": base,
        "Bull": DcfAssumptions(
            discount_rate=max(base.discount_rate - 0.01, base.terminal_growth_rate + 0.02),
            growth_rate=min(base.growth_rate + 0.03, 0.15),
            terminal_growth_rate=min(base.terminal_growth_rate + 0.005, 0.035),
            projection_years=base.projection_years,
        ),
    }


def calculate_sensitivity_table(
    starting_fcf: float,
    net_debt: Optional[float],
    shares_outstanding: Optional[float],
    base_assumptions: DcfAssumptions,
    discount_rate_steps: Optional[list[float]] = None,
    terminal_growth_steps: Optional[list[float]] = None,
) -> pd.DataFrame:
    if discount_rate_steps is None:
        discount_rate_steps = [-0.02, -0.01, 0.0, 0.01, 0.02]
    if terminal_growth_steps is None:
        terminal_growth_steps = [-0.01, -0.005, 0.0, 0.005, 0.01]

    rows = []
    for terminal_delta in terminal_growth_steps:
        row = {"Terminal Growth": base_assumptions.terminal_growth_rate + terminal_delta}
        for discount_delta in discount_rate_steps:
            discount_rate = base_assumptions.discount_rate + discount_delta
            terminal_growth = base_assumptions.terminal_growth_rate + terminal_delta
            column = discount_rate
            if discount_rate <= terminal_growth or discount_rate - terminal_growth < 0.005:
                row[column] = None
                continue
            assumptions = DcfAssumptions(
                discount_rate=discount_rate,
                growth_rate=base_assumptions.growth_rate,
                terminal_growth_rate=terminal_growth,
                projection_years=base_assumptions.projection_years,
            )
            result = _discounted_cash_flow_from_starting_fcf(
                starting_fcf,
                assumptions,
                net_debt=net_debt,
                shares_outstanding=shares_outstanding,
            )
            row[column] = result.fair_value_per_share if result else None
        rows.append(row)
    return pd.DataFrame(rows)


def reverse_dcf_implied_growth(
    current_price: Optional[float],
    shares_outstanding: Optional[float],
    net_debt: Optional[float],
    starting_fcf: Optional[float],
    discount_rate: float,
    terminal_growth_rate: float,
    projection_years: int,
    low: float = -0.50,
    high: float = 0.50,
) -> ReverseDcfResult:
    if not current_price or not shares_outstanding or starting_fcf in (None, 0):
        return ReverseDcfResult(None, None, None, "Reverse DCF requires price, shares, and starting FCF.", False)
    if discount_rate <= terminal_growth_rate:
        return ReverseDcfResult(None, None, None, "Reverse DCF invalid because discount rate must exceed terminal growth.", False)

    target_equity_value = current_price * shares_outstanding
    target_enterprise_value = target_equity_value + (net_debt or 0)

    def enterprise_for_growth(growth: float) -> float:
        assumptions = DcfAssumptions(discount_rate, growth, terminal_growth_rate, projection_years)
        result = _discounted_cash_flow_from_starting_fcf(
            starting_fcf,
            assumptions,
            net_debt=0,
            shares_outstanding=None,
        )
        return result.enterprise_value if result else float("nan")

    low_value = enterprise_for_growth(low)
    high_value = enterprise_for_growth(high)
    if np.isnan(low_value) or np.isnan(high_value) or not (low_value <= target_enterprise_value <= high_value):
        return ReverseDcfResult(
            None,
            target_enterprise_value,
            target_equity_value,
            "Current price implies a growth rate outside the -50% to +50% search range.",
            False,
        )

    lo, hi = low, high
    for _ in range(80):
        mid = (lo + hi) / 2
        mid_value = enterprise_for_growth(mid)
        if mid_value < target_enterprise_value:
            lo = mid
        else:
            hi = mid
    implied_growth = (lo + hi) / 2
    message = (
        f"At the current price, the market appears to require approximately "
        f"{implied_growth * 100:.1f}% annual FCF growth for {projection_years} years "
        "under the selected discount rate and terminal growth assumptions."
    )
    return ReverseDcfResult(implied_growth, target_enterprise_value, target_equity_value, message, True)
