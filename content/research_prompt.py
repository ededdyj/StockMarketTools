"""Prompt export helpers for single-stock research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.dcf_assumptions import DynamicDcfEstimate
from models.financial_health import FinancialHealthResult
from models.valuation import DcfAssumptions, ValuationResult
from utils.fundamentals import FundamentalsSnapshot


@dataclass(frozen=True)
class StockResearchPromptInputs:
    ticker: str
    company_name: str
    sector: str
    industry: str
    business_summary: str
    current_price: Optional[float]
    market_cap: Optional[float]
    enterprise_value: Optional[float]
    trailing_pe: Optional[float]
    forward_pe: Optional[float]
    price_to_book: Optional[float]
    profit_margins: Optional[float]
    beta: Optional[float]
    dividend_yield: Optional[float]
    payout_ratio: Optional[float]
    fundamentals: FundamentalsSnapshot
    financial_health: FinancialHealthResult
    assumptions: Optional[DcfAssumptions] = None
    default_assumptions: Optional[DcfAssumptions] = None
    dynamic_estimate: Optional[DynamicDcfEstimate] = None
    valuation: Optional[ValuationResult] = None
    fair_value_range: Optional[tuple[float, float]] = None
    timeframe_label: str = ""
    timeframe_note: str = ""


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return value != value
    except TypeError:
        return False


def _money(value: Optional[float], precision: int = 2) -> str:
    if _is_missing(value):
        return "N/A"
    return f"${float(value):,.{precision}f}"


def _number(value: Optional[float], precision: int = 2) -> str:
    if _is_missing(value):
        return "N/A"
    return f"{float(value):,.{precision}f}"


def _percent(value: Optional[float], precision: int = 2) -> str:
    if _is_missing(value):
        return "N/A"
    return f"{float(value) * 100:.{precision}f}%"


def _upside_downside(current_price: Optional[float], fair_value: Optional[float]) -> str:
    if _is_missing(current_price) or _is_missing(fair_value) or not current_price:
        return "N/A"
    return _percent((float(fair_value) - float(current_price)) / float(current_price), 1)


def _trim_summary(summary: str, max_chars: int = 1_200) -> str:
    if not summary:
        return "N/A"
    if len(summary) <= max_chars:
        return summary
    return f"{summary[:max_chars].rstrip()}..."


def _format_assumptions(assumptions: Optional[DcfAssumptions]) -> list[str]:
    if assumptions is None:
        return ["- DCF assumptions unavailable or invalid."]
    return [
        f"- Discount rate: {_percent(assumptions.discount_rate)}",
        f"- Explicit FCF growth rate: {_percent(assumptions.growth_rate)}",
        f"- Terminal growth rate: {_percent(assumptions.terminal_growth_rate)}",
        f"- Projection years: {assumptions.projection_years}",
    ]


def _format_health_signals(result: FinancialHealthResult) -> list[str]:
    rows = []
    for signal in result.signals:
        if signal.passed is None:
            outcome = "N/A"
        elif signal.passed:
            outcome = "Pass"
        else:
            outcome = "Fail"
        rows.append(f"- {signal.category}: {signal.name} = {outcome} ({signal.formula})")
    return rows


def _format_dynamic_lines(dynamic_estimate: Optional[DynamicDcfEstimate]) -> list[str]:
    if dynamic_estimate is None:
        return ["- Dynamic default derivation unavailable."]
    rows = [
        f"- {line.assumption}: {line.value} | Source: {line.source} | Formula: {line.formula}"
        for line in dynamic_estimate.lines
    ]
    if dynamic_estimate.warnings:
        rows.append("")
        rows.append("Dynamic default warnings:")
        rows.extend(f"- {warning}" for warning in dynamic_estimate.warnings)
    return rows


def build_stock_research_prompt(inputs: StockResearchPromptInputs) -> str:
    """Build a copyable prompt containing app context plus research instructions."""

    valuation = inputs.valuation
    fair_value = valuation.fair_value_per_share if valuation else None
    fair_value_range = "N/A"
    if inputs.fair_value_range:
        fair_value_range = f"{_money(inputs.fair_value_range[0])} to {_money(inputs.fair_value_range[1])}"

    fundamentals = inputs.fundamentals
    default_label = "Dynamic defaults"
    if inputs.default_assumptions and inputs.assumptions == inputs.default_assumptions:
        default_label = "Active assumptions match the app-generated dynamic defaults"
    elif inputs.default_assumptions:
        default_label = "User-edited assumptions differ from the app-generated dynamic defaults"

    prompt_lines = [
        f"Research {inputs.ticker} ({inputs.company_name}) as an equity investment.",
        "",
        "Use the app-provided context below as the starting point, then research current external information from primary or high-quality sources. Do not treat the app output as final. Check the latest filings, earnings release, management guidance, investor presentation, recent news, analyst expectations, competitive position, and industry conditions.",
        "",
        "Your task:",
        "1. Verify whether the app's fair value estimate is reasonable.",
        "2. Pull in additional information that could change the valuation, including revenue segment trends, margin drivers, reinvestment needs, debt maturities, share count changes, capital returns, regulatory/legal risks, macro sensitivity, competitive threats, and management guidance.",
        "3. Build your own fair value estimate and price target range. Explain the method, key assumptions, and sensitivity to growth, margins, discount rate, and terminal value.",
        "4. Compare your estimate with the app's DCF fair value estimate and explain the biggest reasons for agreement or disagreement.",
        "5. Conclude with a balanced bull/base/bear case, the most important watch items, and what evidence would change your mind.",
        "",
        "App-provided company context:",
        f"- Ticker: {inputs.ticker}",
        f"- Company: {inputs.company_name}",
        f"- Sector: {inputs.sector}",
        f"- Industry: {inputs.industry}",
        f"- Business summary: {_trim_summary(inputs.business_summary)}",
        "",
        "Market and valuation snapshot from the app:",
        f"- Current/regular market price: {_money(inputs.current_price)}",
        f"- Market cap: {_money(inputs.market_cap, 0)}",
        f"- Yahoo enterprise value: {_money(inputs.enterprise_value, 0)}",
        f"- Trailing P/E: {_number(inputs.trailing_pe)}",
        f"- Forward P/E: {_number(inputs.forward_pe)}",
        f"- Price/book: {_number(inputs.price_to_book)}",
        f"- Profit margin: {_percent(inputs.profit_margins)}",
        f"- Beta: {_number(inputs.beta)}",
        f"- Dividend yield: {_percent(inputs.dividend_yield)}",
        f"- Payout ratio: {_percent(inputs.payout_ratio)}",
        "",
        "App DCF output:",
        f"- App fair value estimate per share: {_money(fair_value)}",
        f"- App fair value sensitivity range: {fair_value_range}",
        f"- Implied upside/downside to app fair value: {_upside_downside(inputs.current_price, fair_value)}",
        f"- App enterprise value estimate: {_money(valuation.enterprise_value, 0) if valuation else 'N/A'}",
        f"- App equity value estimate: {_money(valuation.equity_value, 0) if valuation else 'N/A'}",
        f"- Net debt used by app: {_money(fundamentals.net_debt, 0)}",
        f"- Cash and equivalents used by app: {_money(fundamentals.cash_and_equivalents, 0)}",
        f"- Total debt used by app: {_money(fundamentals.total_debt, 0)}",
        f"- Shares outstanding used by app: {_number(fundamentals.shares_outstanding, 0)}",
        f"- Balance sheet as-of date: {fundamentals.balance_sheet_as_of or 'N/A'}",
        f"- Data pulled at: {fundamentals.pulled_at}",
        f"- Assumption status: {default_label}",
        "",
        "Active DCF assumptions:",
        *_format_assumptions(inputs.assumptions),
        "",
        "Dynamic default derivation shown by the app:",
        *_format_dynamic_lines(inputs.dynamic_estimate),
        "",
        "Financial health score from the app:",
        f"- Score: {inputs.financial_health.score}/{inputs.financial_health.max_score}",
        f"- Available signals: {inputs.financial_health.available_signals}/{inputs.financial_health.max_score}",
        f"- Score ratio: {_percent(inputs.financial_health.score_ratio, 1)}",
        *_format_health_signals(inputs.financial_health),
        "",
        "Known app limitations to account for in your research:",
        "- Yahoo Finance and yfinance data can lag official filings or omit fields.",
        "- The app's DCF is a simplified free-cash-flow model and may not fit banks, insurers, REITs, ETFs, or highly cyclical companies.",
        "- The app does not model segment-level revenue, margins, explicit working-capital needs, stock-based compensation dilution, lease obligations, debt maturity schedules, or management guidance unless those are visible in the downloaded Yahoo fields.",
        "- The app's fair value is a scenario estimate, not investment advice.",
        "",
        "Please cite the sources you use and separate facts, estimates, and your assumptions.",
    ]
    return "\n".join(prompt_lines)
