"""Central definitions for supported investment philosophies.

This module keeps financing assumptions and UI copy close together so the
Streamlit layer can dynamically render descriptions, warnings, metrics, and
default valuation inputs per approach.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class InvestmentPhilosophy:
    """Structured information surfaced throughout the UI."""

    name: str
    description: str
    key_metrics: List[str]
    default_assumptions: Dict[str, float]
    warnings: List[str]
    limitations: List[str]
    tools: List[str] = field(default_factory=list)


PHILOSOPHIES: Dict[str, InvestmentPhilosophy] = {
    "Long-term Value/DCF": InvestmentPhilosophy(
        name="Long-term Value/DCF",
        description=(
            "Focuses on intrinsic value via discounted cash flow. Works best for"
            " companies with stable, positive free cash flow and predictable"
            " growth trajectories."
        ),
        key_metrics=[
            "Enterprise value per share (DCF)",
            "FCF margin & growth",  # possible display in UI
            "Discount to fair value",
        ],
        default_assumptions={
            "discount_rate": 0.10,
            "growth_rate": 0.03,
            "terminal_growth_rate": 0.02,
            "projection_years": 5,
        },
        warnings=[
            "High leverage or negative cash flow reduces reliability.",
            "Results are sensitive to discount/growth rate assumptions.",
        ],
        limitations=[
            "Does not model scenario-specific capital structure changes.",
            "Assumes steady growth rather than cyclical swings.",
        ],
        tools=["Single Stock Analysis", "SP500 Deals"],
    ),
    "Dividend/Income": InvestmentPhilosophy(
        name="Dividend/Income",
        description=(
            "Targets predictable cash distributions today. Emphasizes payout"
            " safety, dividend yield, and coverage."
        ),
        key_metrics=[
            "Dividend yield (%)",
            "Payout ratio",
            "Years of growth and ex-dividend schedule",
        ],
        default_assumptions={
            "required_yield": 0.03,
            "max_payout_ratio": 0.75,
        },
        warnings=[
            "Dividend data may lag one payout cycle on free APIs.",
            "Yield spikes can signal distress rather than opportunity.",
        ],
        limitations=[
            "Does not forecast dividend cuts or buybacks automatically.",
            "Assumes U.S. tax treatment; adjust for local jurisdiction.",
        ],
        tools=["Single Stock Analysis", "Quality vs Value Screener"],
    ),
    "Growth-at-a-Reasonable-Price": InvestmentPhilosophy(
        name="Growth-at-a-Reasonable-Price",
        description=(
            "Seeks companies with durable growth that still trade below"
            " intrinsic value when factoring growth and profitability."
        ),
        key_metrics=[
            "Revenue growth percentile",
            "Return on equity percentile",
            "DCF-implied discount",
        ],
        default_assumptions={
            "min_revenue_growth": 0.10,
            "min_roe": 0.12,
            "value_weight": 0.4,
        },
        warnings=[
            "Growth estimates rely on trailing data, not analyst forecasts.",
            "Very high-growth, unprofitable names may be filtered out.",
        ],
        limitations=[
            "No explicit PEG or SaaS-specific metrics.",
            "Normalizes by percentile, so thin universes can distort ranks.",
        ],
        tools=["Quality vs Value Screener"],
    ),
    "Momentum/Trend": InvestmentPhilosophy(
        name="Momentum/Trend",
        description=(
            "Highlights recent price strength and trend-following signals to"
            " ride prevailing moves rather than intrinsic value."
        ),
        key_metrics=[
            "1M/3M/12M total return",
            "Intraday vs. close trend",
            "Volatility (beta)",
        ],
        default_assumptions={
            "lookback_days": 90,
            "min_trend_strength": 0.05,
        },
        warnings=[
            "Momentum regimes can reverse abruptly.",
            "Does not incorporate stop-loss logic.",
        ],
        limitations=[
            "No risk parity or volatility targeting.",
            "Historical prices sourced from yfinance; split adjustments assumed.",
        ],
        tools=["Single Stock Analysis"],
    ),
    "Index/Passive": InvestmentPhilosophy(
        name="Index/Passive",
        description=(
            "Focuses on broad exposure and diversification. Supports ETF"
            " comparison, allocation hygiene, and cost awareness."
        ),
        key_metrics=[
            "Expense ratio",
            "Tracking difference vs. index",
            "Distribution yield",
        ],
        default_assumptions={
            "max_expense_ratio": 0.0025,
            "rebalance_frequency_months": 6,
        },
        warnings=[
            "ETF holdings data is not retrieved; do external due diligence.",
            "Bond-heavy ETFs respond differently to rate shocks.",
        ],
        limitations=[
            "Does not suggest specific asset allocations.",
            "Requires manually entering ETF tickers.",
        ],
        tools=["Single Stock Analysis"],
    ),
}


def get_philosophy_options() -> List[str]:
    """Return names for the selector."""

    return list(PHILOSOPHIES.keys())


def get_philosophy(name: str) -> InvestmentPhilosophy:
    """Safe lookup that defaults to Long-term Value/DCF."""

    return PHILOSOPHIES.get(name, PHILOSOPHIES["Long-term Value/DCF"])

