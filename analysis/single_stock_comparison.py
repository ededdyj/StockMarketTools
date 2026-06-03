"""Single-stock comparison analysis helpers.

The Streamlit page supplies ticker data. This module keeps parsing, valuation
row construction, ranking, and prompt generation testable without UI code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Callable, Iterable, Optional

import pandas as pd

from analysis.results import SkippedTicker
from models.dcf_fit import calculate_dcf_fit
from models.dcf_warnings import DcfWarning, generate_dcf_warnings
from models.financial_health import calculate_financial_health
from models.free_cash_flow import FreeCashFlowSnapshot, resolve_free_cash_flow
from models.income_metrics import resolve_income_metrics
from models.valuation import DcfAssumptions, calculate_fair_value, calculate_fair_value_range
from utils.fundamentals import extract_fundamentals


DEFAULT_MAX_COMPARISON_TICKERS = 20
DEFAULT_COMPARISON_WEIGHTS = {
    "Value": 0.45,
    "Financial Health": 0.20,
    "Quality": 0.15,
    "Growth": 0.10,
    "Stability": 0.10,
}


@dataclass
class ComparisonResult:
    dataframe: pd.DataFrame
    skipped: list[SkippedTicker] = field(default_factory=list)
    run_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    assumptions: Optional[DcfAssumptions] = None
    weights: dict[str, float] = field(default_factory=lambda: DEFAULT_COMPARISON_WEIGHTS.copy())


def parse_ticker_input(raw_text: str, max_tickers: int = DEFAULT_MAX_COMPARISON_TICKERS) -> list[str]:
    """Parse comma, whitespace, or newline separated tickers into unique uppercase symbols."""

    if not raw_text:
        return []

    parsed: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[\s,]+", raw_text.upper().strip()):
        ticker = token.strip()
        if not ticker:
            continue
        if ticker not in seen:
            parsed.append(ticker)
            seen.add(ticker)
        if len(parsed) >= max_tickers:
            break
    return parsed


def _prefer_current_statement_frame(annual_frame: pd.DataFrame, quarterly_frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(quarterly_frame, pd.DataFrame) and not quarterly_frame.empty:
        return quarterly_frame
    return annual_frame


def _safe_frame(data: dict, key: str) -> pd.DataFrame:
    frame = data.get(key, pd.DataFrame())
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _safe_ratio(value) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    if result > 1:
        result /= 100.0
    return result


def _format_pct(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def _format_money(value: Optional[float]) -> str:
    return "N/A" if value is None else f"${value:,.2f}"


def _warning_counts(warnings: Iterable[DcfWarning]) -> tuple[int, int, int]:
    high = medium = low = 0
    for warning in warnings:
        if warning.severity == "High":
            high += 1
        elif warning.severity == "Medium":
            medium += 1
        elif warning.severity == "Low":
            low += 1
    return high, medium, low


def build_comparison_row(
    ticker: str,
    data: dict,
    assumptions: DcfAssumptions,
    philosophy_name: str = "",
) -> tuple[Optional[dict], Optional[SkippedTicker]]:
    """Build one comparison row from already-fetched stock data."""

    if not data:
        return None, SkippedTicker(ticker, "no_usable_data", "No data returned for ticker.")

    info = data.get("info") or {}
    financials = _safe_frame(data, "financials")
    quarterly_financials = _safe_frame(data, "quarterly_financials")
    cashflow = _safe_frame(data, "cashflow")
    quarterly_cashflow = _safe_frame(data, "quarterly_cashflow")
    ttm_cashflow = _safe_frame(data, "ttm_cashflow")
    balance_sheet = _safe_frame(data, "balance_sheet")
    quarterly_balance_sheet = _safe_frame(data, "quarterly_balance_sheet")
    sec_fcf_snapshot = data.get("sec_fcf_snapshot")
    sec_warnings = list(data.get("sec_warnings") or []) + list(data.get("sec_fcf_warnings") or [])

    if not info and financials.empty and cashflow.empty and balance_sheet.empty:
        return None, SkippedTicker(ticker, "no_usable_data", "Missing profile and statement data.")

    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    try:
        current_price = float(current_price) if current_price is not None else None
    except (TypeError, ValueError):
        current_price = None

    valuation_financials = _prefer_current_statement_frame(financials, quarterly_financials)
    valuation_balance_sheet = _prefer_current_statement_frame(balance_sheet, quarterly_balance_sheet)
    fundamentals = extract_fundamentals(info, valuation_balance_sheet, financials=valuation_financials)
    income_metrics = resolve_income_metrics(
        info,
        annual_financials=financials,
        quarterly_financials=quarterly_financials,
        shares_outstanding=fundamentals.shares_outstanding,
    )
    financial_health = calculate_financial_health(financials, balance_sheet, cashflow)
    fcf_snapshot = resolve_free_cash_flow(
        cashflow,
        method="best_available",
        quarterly_cashflow=quarterly_cashflow,
        ttm_cashflow=ttm_cashflow,
        sec_fcf_snapshot=sec_fcf_snapshot if isinstance(sec_fcf_snapshot, FreeCashFlowSnapshot) else None,
    )

    valuation = None
    fair_value_range = None
    if fcf_snapshot.value is not None:
        valuation = calculate_fair_value(
            cashflow,
            net_debt=fundamentals.net_debt,
            shares_outstanding=fundamentals.shares_outstanding,
            assumptions=assumptions,
            starting_fcf=fcf_snapshot.value,
        )
        fair_value_range = calculate_fair_value_range(
            cashflow,
            net_debt=fundamentals.net_debt,
            shares_outstanding=fundamentals.shares_outstanding,
            assumptions=assumptions,
            starting_fcf=fcf_snapshot.value,
        )

    dcf_warnings = generate_dcf_warnings(
        info,
        fundamentals,
        assumptions,
        fcf_snapshot,
        financials=valuation_financials,
        cashflow=cashflow,
        income_metrics=income_metrics,
        sec_warnings=sec_warnings,
        philosophy_name=philosophy_name,
    )
    dcf_fit = calculate_dcf_fit(info, fundamentals, fcf_snapshot, dcf_warnings)
    high_warnings, medium_warnings, low_warnings = _warning_counts(dcf_warnings)
    fair_value = valuation.fair_value_per_share if valuation else None
    upside_downside = None
    if current_price and fair_value is not None:
        upside_downside = (fair_value - current_price) / current_price

    range_text = "N/A"
    if fair_value_range and all(value is not None for value in fair_value_range):
        range_text = f"{_format_money(fair_value_range[0])} to {_format_money(fair_value_range[1])}"

    missing_notes = []
    if current_price is None:
        missing_notes.append("Missing current price")
    if fair_value is None:
        missing_notes.append("Missing DCF fair value")
    if fcf_snapshot.value is None:
        missing_notes.append("Missing starting FCF")
    if fundamentals.shares_outstanding is None:
        missing_notes.append("Missing share count")
    if financial_health.available_signals < financial_health.max_score:
        missing_notes.append(
            f"{financial_health.max_score - financial_health.available_signals} unavailable health signals"
        )
    missing_notes.extend(fundamentals.note_tags)
    missing_notes.extend(f"{warning.severity}: {warning.message}" for warning in dcf_warnings if warning.severity in {"High", "Medium"})

    return {
        "Ticker": ticker,
        "Company": info.get("longName") or info.get("shortName") or "",
        "Sector": info.get("sector") or "",
        "Industry": info.get("industry") or "",
        "Current Price": current_price,
        "App Fair Value": fair_value,
        "Fair Value Range": range_text,
        "Upside/Downside %": upside_downside,
        "Margin of Safety %": upside_downside,
        "Market Cap": info.get("marketCap"),
        "Trailing PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "Price to Book": info.get("priceToBook"),
        "Profit Margin": _safe_ratio(info.get("profitMargins")),
        "Beta": info.get("beta"),
        "Dividend Yield": _safe_ratio(info.get("dividendYield")),
        "Payout Ratio": _safe_ratio(info.get("payoutRatio")),
        "Starting FCF": fcf_snapshot.value,
        "Starting FCF Source": f"{fcf_snapshot.source}; {fcf_snapshot.period or 'period N/A'}",
        "DCF Assumptions Used": (
            f"Discount {_format_pct(assumptions.discount_rate)}, "
            f"Growth {_format_pct(assumptions.growth_rate)}, "
            f"Terminal {_format_pct(assumptions.terminal_growth_rate)}, "
            f"{assumptions.projection_years} years"
        ),
        "DCF Fit Label": dcf_fit.label,
        "DCF Fit Score": dcf_fit.score,
        "Financial Health Raw Score": financial_health.score,
        "Financial Health Normalized Score": financial_health.score_ratio,
        "ROE": _safe_ratio(info.get("returnOnEquity")),
        "Revenue Growth": _safe_ratio(info.get("revenueGrowth")),
        "Debt-to-Equity": info.get("debtToEquity"),
        "Net Debt": fundamentals.net_debt,
        "Data Freshness Summary": (
            f"Balance sheet {fundamentals.balance_sheet_as_of or 'N/A'}; "
            f"FCF period {fcf_snapshot.period or 'N/A'}; pulled {fundamentals.pulled_at or 'N/A'}"
        ),
        "Data-Quality Warning Count": len(dcf_warnings),
        "High/Medium Warning Count": high_warnings + medium_warnings,
        "High Warning Count": high_warnings,
        "Medium Warning Count": medium_warnings,
        "Low Warning Count": low_warnings,
        "Missing Data / Warnings": "; ".join(dict.fromkeys(missing_notes)),
    }, None


def _rank_percentile(series: pd.Series, ascending: bool = True, missing_score: float = 0.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    ranked = numeric.rank(pct=True, ascending=ascending)
    return ranked.fillna(missing_score).clip(0.0, 1.0)


def _value_score(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    capped = numeric.clip(lower=-1.0, upper=1.5)
    normalized = (capped + 1.0) / 2.5
    return normalized.fillna(0.0).clip(0.0, 1.0)


def score_comparison_rows(
    rows: list[dict] | pd.DataFrame,
    weights: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    """Score and rank comparison rows from best model-based value to worst."""

    weights = weights or DEFAULT_COMPARISON_WEIGHTS
    df = pd.DataFrame(rows).copy()
    if df.empty:
        return df

    df["Value Score"] = _value_score(df.get("Upside/Downside %"))
    df["Financial Health Score"] = pd.to_numeric(df.get("Financial Health Normalized Score"), errors="coerce").fillna(0.0).clip(0.0, 1.0)
    df["Quality Score"] = _rank_percentile(df.get("ROE"), ascending=True, missing_score=0.0)
    profitability_score = _rank_percentile(df.get("Profit Margin"), ascending=True, missing_score=0.0)
    df["Quality Score"] = ((df["Quality Score"] + profitability_score) / 2).fillna(0.0)
    df["Growth Score"] = _rank_percentile(df.get("Revenue Growth"), ascending=True, missing_score=0.0)
    df["Stability Score"] = _rank_percentile(df.get("Debt-to-Equity"), ascending=False, missing_score=0.5)
    df["Warning Penalty"] = (
        pd.to_numeric(df.get("High Warning Count"), errors="coerce").fillna(0) * 0.12
        + pd.to_numeric(df.get("Medium Warning Count"), errors="coerce").fillna(0) * 0.04
        + (pd.to_numeric(df.get("App Fair Value"), errors="coerce").isna()).astype(float) * 0.25
        + (pd.to_numeric(df.get("Current Price"), errors="coerce").isna()).astype(float) * 0.15
    ).clip(0.0, 0.60)
    df["Overall Comparison Score"] = (
        weights.get("Value", 0.45) * df["Value Score"]
        + weights.get("Financial Health", 0.20) * df["Financial Health Score"]
        + weights.get("Quality", 0.15) * df["Quality Score"]
        + weights.get("Growth", 0.10) * df["Growth Score"]
        + weights.get("Stability", 0.10) * df["Stability Score"]
        - df["Warning Penalty"]
    ).clip(0.0, 1.0)

    def verdict(row: pd.Series) -> str:
        if pd.isna(row.get("App Fair Value")):
            return "Incomplete valuation data"
        if row["Overall Comparison Score"] >= 0.70:
            return "Best value candidate"
        if row["Overall Comparison Score"] >= 0.50:
            return "Worth deeper review"
        if row["Overall Comparison Score"] >= 0.30:
            return "Mixed model signal"
        return "Weakest model signal"

    def reason(row: pd.Series) -> str:
        parts = []
        upside = row.get("Upside/Downside %")
        if pd.notna(upside):
            parts.append(f"{upside:.1%} app DCF upside/downside")
        else:
            parts.append("No app DCF upside available")
        parts.append(f"health {row.get('Financial Health Score', 0):.2f}")
        if row.get("Warning Penalty", 0) > 0:
            parts.append(f"warning penalty {row.get('Warning Penalty', 0):.2f}")
        return "; ".join(parts)

    df["Model Verdict"] = df.apply(verdict, axis=1)
    df["Key Reason"] = df.apply(reason, axis=1)
    df = df.sort_values("Overall Comparison Score", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df


def compare_single_stocks(
    tickers: Iterable[str],
    assumptions: DcfAssumptions,
    data_loader: Callable[[str], dict],
    weights: Optional[dict[str, float]] = None,
    philosophy_name: str = "",
) -> ComparisonResult:
    """Fetch supplied tickers through data_loader, build rows, and rank them."""

    rows: list[dict] = []
    skipped: list[SkippedTicker] = []
    for ticker in tickers:
        try:
            row, skipped_ticker = build_comparison_row(
                ticker,
                data_loader(ticker),
                assumptions=assumptions,
                philosophy_name=philosophy_name,
            )
            if row is not None:
                rows.append(row)
            if skipped_ticker is not None:
                skipped.append(skipped_ticker)
        except Exception as exc:
            skipped.append(SkippedTicker(ticker, "analysis_exception", str(exc)))

    return ComparisonResult(
        dataframe=score_comparison_rows(rows, weights=weights),
        skipped=skipped,
        assumptions=assumptions,
        weights=weights or DEFAULT_COMPARISON_WEIGHTS.copy(),
    )


def build_single_stock_comparison_prompt(
    result: ComparisonResult,
    input_tickers: Iterable[str],
) -> str:
    """Build a copyable validation prompt for an app-generated comparison."""

    df = result.dataframe
    assumptions = result.assumptions or DcfAssumptions.defaults()
    weights = result.weights or DEFAULT_COMPARISON_WEIGHTS
    lines = [
        "Research this app-generated stock comparison as an equity investment ranking. Use the app output below as a starting point, then validate with current external information from primary or high-quality sources. Do not treat the app ranking as final.",
        "",
        "Your tasks:",
        "1. Verify the latest SEC filings, earnings releases, investor presentations, management guidance, and recent news for every company.",
        "2. Check whether newer information exists after the app's financial-statement and free-cash-flow dates.",
        "3. Validate revenue trends, margins, reinvestment needs, debt maturities, share count changes, buybacks/dividends, legal/regulatory risks, macro sensitivity, and competitive position.",
        "4. Build your own independent ranking from best buy today to worst among the same tickers.",
        "5. Explain where you agree or disagree with the app ranking and what evidence would change the ranking.",
        "6. Produce bull/base/bear notes for each ticker, or at least the top 3 and bottom 1.",
        "",
        "App comparison run:",
        f"- Input tickers: {', '.join(input_tickers)}",
        f"- Run timestamp: {result.run_timestamp}",
        "- Ranking label: Best Value Today According to App Data",
        (
            "- Scoring formula: "
            f"Value/upside {weights.get('Value', 0):.0%}, "
            f"Financial health {weights.get('Financial Health', 0):.0%}, "
            f"Quality {weights.get('Quality', 0):.0%}, "
            f"Growth {weights.get('Growth', 0):.0%}, "
            f"Stability/leverage {weights.get('Stability', 0):.0%}; "
            "then subtract warning and missing-data penalties."
        ),
        (
            "- DCF assumptions used: "
            f"discount rate {assumptions.discount_rate:.2%}, "
            f"growth rate {assumptions.growth_rate:.2%}, "
            f"terminal growth {assumptions.terminal_growth_rate:.2%}, "
            f"projection years {assumptions.projection_years}."
        ),
        "",
        "App ranking output:",
    ]

    if df.empty:
        lines.append("- No ranked rows were produced.")
    else:
        prompt_cols = [
            "Rank",
            "Ticker",
            "Company",
            "Current Price",
            "App Fair Value",
            "Upside/Downside %",
            "Financial Health Score",
            "Quality Score",
            "Growth Score",
            "Stability Score",
            "Warning Penalty",
            "Overall Comparison Score",
            "DCF Assumptions Used",
            "Data Freshness Summary",
            "Missing Data / Warnings",
            "Model Verdict",
            "Key Reason",
        ]
        for _, row in df[prompt_cols].iterrows():
            lines.append(
                "- "
                f"#{int(row['Rank'])} {row['Ticker']} ({row.get('Company') or 'Company N/A'}): "
                f"price {_format_money(row.get('Current Price'))}, "
                f"app fair value {_format_money(row.get('App Fair Value'))}, "
                f"upside/downside {_format_pct(row.get('Upside/Downside %'))}, "
                f"health {row.get('Financial Health Score', 0):.2f}, "
                f"quality {row.get('Quality Score', 0):.2f}, "
                f"growth {row.get('Growth Score', 0):.2f}, "
                f"stability {row.get('Stability Score', 0):.2f}, "
                f"penalty {row.get('Warning Penalty', 0):.2f}, "
                f"overall {row.get('Overall Comparison Score', 0):.2f}. "
                f"Freshness: {row.get('Data Freshness Summary') or 'N/A'}. "
                f"Warnings/missing data: {row.get('Missing Data / Warnings') or 'None listed'}. "
                f"App verdict: {row.get('Model Verdict')}. Key reason: {row.get('Key Reason')}."
            )

    lines.extend(["", "Skipped tickers:"])
    if result.skipped:
        for skipped in result.skipped:
            detail = f" ({skipped.detail})" if skipped.detail else ""
            lines.append(f"- {skipped.ticker}: {skipped.reason}{detail}")
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "Known app limitations:",
            "- The app ranking is model-based and is not investment advice or a guaranteed buy recommendation.",
            "- DCF is a simplified free-cash-flow model and may not fit banks, insurers, REITs, ETFs, or highly cyclical companies.",
            "- Yahoo Finance and SEC fallback data can be stale, incomplete, throttled, or inconsistent.",
            "- The app does not model segment-level revenue, management guidance, debt maturity schedules, legal/regulatory developments, or all capital-allocation changes.",
            "- Treat the app output as a triage list for research, not a final investment decision.",
        ]
    )
    return "\n".join(lines)
