"""Prompt export helpers for single-stock research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.dcf_assumptions import DynamicDcfEstimate
from models.dcf_warnings import DcfWarning
from models.free_cash_flow import FreeCashFlowSnapshot
from models.financial_health import FinancialHealthResult
from models.valuation import DcfAssumptions, ReverseDcfResult, ScenarioValuation, ValuationResult
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
    fcf_snapshot: Optional[FreeCashFlowSnapshot] = None
    dcf_warnings: list[DcfWarning] = None
    scenarios: list[ScenarioValuation] = None
    sensitivity_table: object = None
    reverse_dcf: Optional[ReverseDcfResult] = None
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


def _format_share_candidates(fundamentals: FundamentalsSnapshot) -> list[str]:
    resolution = fundamentals.share_resolution
    if not resolution:
        return ["- Share-count diagnostics unavailable."]
    rows = [
        f"- Selected shares: {_number(resolution.selected_shares, 0)} from {resolution.selected_shares_source or 'N/A'} ({resolution.selected_shares_date_or_period or 'N/A'})",
        f"- Implied shares from market cap / price: {_number(resolution.implied_shares_from_market_cap, 0)}",
        f"- Selected-vs-implied difference: {_percent(resolution.selected_vs_implied_pct_diff, 1)}",
        "- Candidates considered:",
    ]
    rows.extend(
        f"  - {candidate.source}: {_number(candidate.value, 0)} | {candidate.date_or_period or 'N/A'} | {candidate.formula}"
        for candidate in resolution.candidates
    )
    if resolution.warnings:
        rows.append("- Share-count warnings:")
        rows.extend(f"  - {warning}" for warning in resolution.warnings)
    return rows


def _format_dcf_warnings(warnings: Optional[list[DcfWarning]]) -> list[str]:
    if not warnings:
        return ["- No DCF data-quality warnings generated by the app."]
    return [f"- {warning.severity} | {warning.category}: {warning.message}" for warning in warnings]


def _format_equity_bridge(valuation: Optional[ValuationResult], fundamentals: FundamentalsSnapshot) -> list[str]:
    if valuation is None:
        return ["- Equity bridge unavailable because valuation did not complete."]
    rows = [
        f"- Starting FCF: {_money(valuation.starting_fcf, 0)}",
        f"- PV of explicit FCF: {_money(valuation.pv_explicit_fcf, 0)}",
        f"- Terminal value: {_money(valuation.terminal_value, 0)}",
        f"- PV of terminal value: {_money(valuation.pv_terminal_value, 0)}",
        f"- Enterprise value: {_money(valuation.enterprise_value, 0)}",
        f"- Cash and equivalents: {_money(fundamentals.cash_and_equivalents, 0)}",
        f"- Total debt: {_money(fundamentals.total_debt, 0)}",
        f"- Net debt: {_money(fundamentals.net_debt, 0)}",
        f"- Equity value: {_money(valuation.equity_value, 0)}",
        f"- Shares used: {_number(valuation.shares_used, 0)}",
        f"- Fair value per share: {_money(valuation.fair_value_per_share)}",
    ]
    rows.append("- Projected FCF by year:")
    rows.extend(f"  - Year {index}: {_money(value, 0)}" for index, value in enumerate(valuation.projected_fcf, start=1))
    return rows


def _format_fcf_snapshot(snapshot: Optional[FreeCashFlowSnapshot]) -> list[str]:
    if snapshot is None:
        return ["- FCF source unavailable."]
    return [
        f"- Starting FCF selected: {_money(snapshot.value, 0)}",
        f"- Source: {snapshot.source}",
        f"- Period: {snapshot.period or 'N/A'}",
        f"- Operating cash flow: {_money(snapshot.operating_cash_flow, 0)}",
        f"- Capital expenditures: {_money(snapshot.capital_expenditures, 0)}",
        f"- Formula: {snapshot.formula}",
        "- Capex note: yfinance often reports capital expenditures as a negative cash-flow line; the app treats capex as an outflow and subtracts its absolute value.",
        *[f"- Warning: {warning}" for warning in snapshot.warnings],
    ]


def _format_scenarios(scenarios: Optional[list[ScenarioValuation]]) -> list[str]:
    if not scenarios:
        return ["- Scenario DCF unavailable."]
    rows = []
    for scenario in scenarios:
        valuation = scenario.valuation
        rows.append(
            f"- {scenario.name}: fair value {_money(valuation.fair_value_per_share) if valuation else 'N/A'}, "
            f"growth {_percent(scenario.assumptions.growth_rate)}, discount {_percent(scenario.assumptions.discount_rate)}, "
            f"terminal {_percent(scenario.assumptions.terminal_growth_rate)}, upside/downside {_percent(scenario.upside_downside, 1)}"
        )
        if scenario.warnings:
            rows.extend(f"  - Warning: {warning}" for warning in scenario.warnings)
    return rows


def _format_sensitivity(table) -> list[str]:
    if table is None or getattr(table, "empty", True):
        return ["- Sensitivity table unavailable."]
    rows = []
    for _, row in table.iterrows():
        cells = []
        for column, value in row.items():
            if column == "Terminal Growth":
                continue
            cells.append(f"discount {_percent(column, 1)} = {_money(value) if value == value else 'Invalid'}")
        rows.append(f"- Terminal {_percent(row['Terminal Growth'], 1)}: " + "; ".join(cells))
    return rows


def _format_source_metadata(inputs: StockResearchPromptInputs) -> list[str]:
    fundamentals = inputs.fundamentals
    fcf = inputs.fcf_snapshot
    rows = [
        f"- Current price: {_money(inputs.current_price)} | Source: Yahoo Finance market snapshot",
        f"- Market cap: {_money(inputs.market_cap, 0)} | Source: Yahoo Finance profile",
        f"- Shares used: {_number(fundamentals.shares_outstanding, 0)} | Source: {fundamentals.shares_source or 'N/A'} | Period: {fundamentals.shares_date_or_period or 'N/A'}",
        f"- Implied shares: {_number(fundamentals.implied_shares_from_market_cap, 0)} | Source: computed as market cap / current price",
        f"- Cash: {_money(fundamentals.cash_and_equivalents, 0)} | Source: {fundamentals.cash_source or 'fallback/missing'} | Period: {fundamentals.balance_sheet_as_of or 'N/A'}",
        f"- Total debt: {_money(fundamentals.total_debt, 0)} | Source: {fundamentals.debt_source or 'fallback/missing'} | Period: {fundamentals.balance_sheet_as_of or 'N/A'}",
        f"- Net debt: {_money(fundamentals.net_debt, 0)} | Source: computed as total debt - cash",
    ]
    if fcf:
        rows.extend(
            [
                f"- Operating cash flow: {_money(fcf.operating_cash_flow, 0)} | Source: {fcf.source} | Period: {fcf.period or 'N/A'}",
                f"- Capital expenditures: {_money(fcf.capital_expenditures, 0)} | Source: {fcf.source} | Period: {fcf.period or 'N/A'}",
                f"- Free cash flow: {_money(fcf.value, 0)} | Formula: {fcf.formula}",
            ]
        )
    if inputs.dynamic_estimate:
        for line in inputs.dynamic_estimate.lines:
            if line.assumption in {"Risk-free rate", "Equity risk premium", "Discount rate", "Growth rate", "Terminal growth"}:
                rows.append(f"- {line.assumption}: {line.value} | Source: {line.source} | Formula: {line.formula}")
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
        "Full app DCF equity bridge:",
        *_format_equity_bridge(valuation, fundamentals),
        "",
        "Free-cash-flow source selection:",
        *_format_fcf_snapshot(inputs.fcf_snapshot),
        "",
        "Share-count diagnostics:",
        *_format_share_candidates(fundamentals),
        "",
        "DCF data-quality warnings:",
        *_format_dcf_warnings(inputs.dcf_warnings),
        "",
        "Major valuation input source metadata:",
        *_format_source_metadata(inputs),
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
        "Bull/base/bear scenario output from the app:",
        *_format_scenarios(inputs.scenarios),
        "",
        "DCF sensitivity table from the app:",
        *_format_sensitivity(inputs.sensitivity_table),
        "",
        "Reverse DCF from the app:",
        f"- {inputs.reverse_dcf.message if inputs.reverse_dcf else 'Reverse DCF unavailable.'}",
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
