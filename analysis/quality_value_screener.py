import logging
from pathlib import Path
import time
from typing import List

import pandas as pd
import streamlit as st
import yfinance as yf

from models.valuation import calculate_fair_value, DcfAssumptions
from models.financial_health import calculate_financial_health
from utils.fundamentals import extract_fundamentals
from config.philosophies import get_philosophy
from utils.paths import DATA_DIR
from data.sec_facts import add_sec_fallback_to_statements
from analysis.results import BatchAnalysisResult, SkippedTicker

logger = logging.getLogger(__name__)

"""
Quality vs. Value Screener (CSV‑based, auto‑discover)
=====================================================

* Scans the **data/** folder for any file whose name ends with
  `_tickers.csv` and turns each into a selectable universe (e.g.
  `sp500_tickers.csv` → “Sp500”).
* Sidebar lets the user choose one of those universes **or** upload their
  own CSV; an uploaded file overrides the preset list.
* Pulls fundamental data with *yfinance*, ranks stocks by a composite
  score, and returns a `pandas.DataFrame` for display.
* No dynamic scraping of index constituents—everything is offline except
  the per‑ticker yfinance calls.
"""

# ---------------------------------------------------------------------------
# 1. Discover available CSV lists at startup
# ---------------------------------------------------------------------------

def _discover_csv_paths(folder=DATA_DIR) -> dict[str, str]:
    """Return a mapping {Pretty Name → full path} for every *_tickers.csv
    found in *folder*."""
    paths: dict[str, str] = {}
    if folder is None:
        folder_path = DATA_DIR
    else:
        folder_path = Path(folder)
        if not folder_path.is_absolute():
            folder_path = Path.cwd() / folder_path
    if folder_path.is_dir():
        for path in folder_path.iterdir():
            fname = path.name
            if fname.lower().endswith("_tickers.csv"):
                key = fname[:-12]  # strip _tickers.csv
                key = key.replace("_", " ").replace("-", " ").title()
                paths[key] = str(path)
    return paths

CSV_PATHS = _discover_csv_paths()
GARP_PHILOSOPHY = get_philosophy("Growth-at-a-Reasonable-Price")
GARP_ASSUMPTIONS = GARP_PHILOSOPHY.default_assumptions
MIN_ROE = GARP_ASSUMPTIONS.get("min_roe", 0.12)
MIN_REVENUE_GROWTH = GARP_ASSUMPTIONS.get("min_revenue_growth", 0.10)
VALUE_WEIGHT = GARP_ASSUMPTIONS.get("value_weight", 0.4)
DEFAULT_OTHER_WEIGHTS = (0.25, 0.15, 0.10)
FINANCIAL_HEALTH_WEIGHT = GARP_ASSUMPTIONS.get("financial_health_weight", 0.15)
VALUE_WEIGHT = min(VALUE_WEIGHT, 1.0 - FINANCIAL_HEALTH_WEIGHT)
remaining_weight = max(0.0, 1.0 - VALUE_WEIGHT - FINANCIAL_HEALTH_WEIGHT)
scale = remaining_weight / sum(DEFAULT_OTHER_WEIGHTS) if sum(DEFAULT_OTHER_WEIGHTS) else 1.0
QUALITY_WEIGHT = DEFAULT_OTHER_WEIGHTS[0] * scale
GROWTH_WEIGHT = DEFAULT_OTHER_WEIGHTS[1] * scale
STABILITY_WEIGHT = DEFAULT_OTHER_WEIGHTS[2] * scale
SCREENER_DCF_ASSUMPTIONS = DcfAssumptions.defaults()
DEFAULT_MAX_TICKERS_PER_RUN = 60
DEFAULT_REQUEST_DELAY_SECONDS = 0.5
RATE_LIMIT_STOP_AFTER = 3

# ---------------------------------------------------------------------------
# 2. Ticker‑list loader
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_tickers_from_csv(path: str) -> List[str]:
    """Read *path* and return a list of unique tickers.
    Accepts common column names (Symbol/Ticker) or falls back to the first
    column."""
    df = pd.read_csv(path)
    for col in ["Symbol", "Ticker", "symbol", "ticker"]:
        if col in df.columns:
            return df[col].dropna().unique().tolist()
    return df.iloc[:, 0].dropna().unique().tolist()


@st.cache_data(show_spinner=False)
def get_tickers(universe: str, uploaded_file=None) -> List[str]:
    """Return the ticker list based on *universe* or an uploaded CSV."""

    # 1️⃣  Uploaded CSV overrides preset lists
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            return df.iloc[:, 0].dropna().unique().tolist()
        except Exception as e:
            st.error(f"Could not read uploaded file: {e}")
            return []

    # 2️⃣  Preset CSV based on universe
    csv_path = CSV_PATHS.get(universe)
    if not csv_path:
        st.error(f"Unknown universe: {universe}")
        return []
    try:
        return _load_tickers_from_csv(csv_path)
    except Exception as e:
        st.error(f"Error loading {universe} tickers: {e}")
        return []


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in [
            "too many requests",
            "rate limited",
            "rate limit",
            "429",
            "try after a while",
        ]
    )


def _safe_statement_frame(stock, attribute: str) -> pd.DataFrame:
    try:
        frame = getattr(stock, attribute, pd.DataFrame())
    except Exception:
        return pd.DataFrame()
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()

# ---------------------------------------------------------------------------
# 3. Main Streamlit entry point
# ---------------------------------------------------------------------------

def analyze_quality_value_screener(assumptions: DcfAssumptions = SCREENER_DCF_ASSUMPTIONS) -> BatchAnalysisResult:
    """Run the screener and return a ranked DataFrame."""

    # ── Sidebar UI ──────────────────────────────────────────────────────
    st.sidebar.subheader("Universe")
    options = list(CSV_PATHS.keys())
    if not options:
        st.error("No *_tickers.csv files found in the data/ folder.")
        return BatchAnalysisResult(None)

    default_index = options.index("Dow 30") if "Dow 30" in options else 0
    universe = st.sidebar.selectbox("Choose a list of tickers", options, index=default_index)
    uploaded_file = st.sidebar.file_uploader("…or upload a CSV with tickers", type="csv")
    max_tickers = int(
        st.sidebar.number_input(
            "Max tickers this run",
            min_value=1,
            max_value=500,
            value=min(DEFAULT_MAX_TICKERS_PER_RUN, 500),
            step=10,
            help="Yahoo Finance rate-limits large batch screens. Run smaller batches and wait between runs.",
        )
    )
    start_at = int(
        st.sidebar.number_input(
            "Start at ticker #",
            min_value=1,
            max_value=500,
            value=1,
            step=1,
            help="Use this to continue a large universe in chunks after the previous run completes.",
        )
    )
    request_delay = float(
        st.sidebar.number_input(
            "Delay between Yahoo calls (sec)",
            min_value=0.0,
            max_value=10.0,
            value=DEFAULT_REQUEST_DELAY_SECONDS,
            step=0.25,
            help="Higher values reduce rate-limit risk but make the screener slower.",
        )
    )

    tickers = get_tickers(universe, uploaded_file)
    if not tickers:
        st.warning("No tickers found for the selected universe.")
        return BatchAnalysisResult(None)
    original_total = len(tickers)
    tickers = tickers[start_at - 1 : start_at - 1 + max_tickers]
    if not tickers:
        st.warning("Start position is beyond the selected ticker list.")
        return BatchAnalysisResult(None)
    st.caption(
        f"Screening {len(tickers)} of {original_total} tickers. "
        "Yahoo Finance can rate-limit large runs; use smaller chunks if rate limits appear."
    )

    # ── Analysis loop ───────────────────────────────────────────────────
    results = []
    skipped = []
    progress_bar = st.progress(0)
    total = len(tickers)
    consecutive_rate_limits = 0

    for i, ticker in enumerate(tickers):
        try:
            if request_delay and i > 0:
                time.sleep(request_delay)
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            financials = _safe_statement_frame(stock, "financials")
            cashflow = _safe_statement_frame(stock, "cashflow")
            balance_sheet = _safe_statement_frame(stock, "balance_sheet")

            # Skip if we cannot price the security at all
            if current_price is None:
                skipped.append(SkippedTicker(ticker, "missing_price"))
                continue
            if cashflow is None or cashflow.empty:
                skipped.append(SkippedTicker(ticker, "missing_cashflow"))
                continue

            (
                health_financials,
                health_balance_sheet,
                health_cashflow,
                financial_health_source,
                sec_warnings,
            ) = add_sec_fallback_to_statements(ticker, financials, balance_sheet, cashflow)
            fundamentals = extract_fundamentals(info, balance_sheet, financials=financials)
            financial_health = calculate_financial_health(health_financials, health_balance_sheet, health_cashflow)
            valuation = calculate_fair_value(
                cashflow,
                net_debt=fundamentals.net_debt,
                shares_outstanding=fundamentals.shares_outstanding,
                assumptions=assumptions,
            )
            if valuation is None:
                skipped.append(SkippedTicker(ticker, "valuation_failed"))
                continue

            fair_value = valuation.fair_value_per_share
            if fair_value is not None and fair_value > 0:
                discount_pct = ((fair_value - current_price) / current_price) * 100
                value_score = max((fair_value - current_price) / fair_value, 0)
            else:
                discount_pct = None
                value_score = 0

            # Raw metrics --------------------------------------------------
            roe = info.get("returnOnEquity")
            if roe is not None and roe > 1:
                roe /= 100.0

            rev_growth = info.get("revenueGrowth")
            if rev_growth is not None and rev_growth > 1:
                rev_growth /= 100.0

            d2e = info.get("debtToEquity")

            meets_roe_target = roe is not None and roe >= MIN_ROE
            meets_growth_target = rev_growth is not None and rev_growth >= MIN_REVENUE_GROWTH

            results.append({
                "Ticker": ticker,
                "Company": info.get("longName", ""),
                "Current Price": current_price,
                "Fair Value": fair_value,
                "Discount (%)": discount_pct,
                "Value Score": value_score,
                "Financial Health Raw Score": financial_health.score,
                "Financial Health Available Signals": financial_health.available_signals,
                "Financial Health Score": financial_health.score_ratio,
                "Financial Health Source": financial_health_source,
                "Net Debt": fundamentals.net_debt,
                "Raw ROE": roe,
                "Raw Revenue Growth": rev_growth,
                "Raw Debt‑to‑Equity": d2e,
                "Meets ROE Target": meets_roe_target,
                "Meets Growth Target": meets_growth_target,
                "Financial Health Details": "; ".join(
                    f"{signal.name}: {'N/A' if signal.passed is None else 'Pass' if signal.passed else 'Fail'}"
                    for signal in financial_health.signals
                ),
                "Fundamental Notes": " | ".join(
                    [*fundamentals.note_tags, *sec_warnings]
                ) if fundamentals.note_tags or sec_warnings else "",
            })
            consecutive_rate_limits = 0
        except Exception as exc:
            if _is_rate_limit_error(exc):
                logger.warning("Yahoo rate limit while analyzing %s: %s", ticker, exc)
                skipped.append(SkippedTicker(ticker, "rate_limited", str(exc)))
                consecutive_rate_limits += 1
                if consecutive_rate_limits >= RATE_LIMIT_STOP_AFTER:
                    remaining = tickers[i + 1 :]
                    skipped.extend(
                        SkippedTicker(symbol, "not_run_rate_limit_stop", "Stopped after repeated Yahoo rate-limit responses.")
                        for symbol in remaining
                    )
                    st.warning(
                        "Yahoo Finance is rate-limiting this screener run. "
                        f"Stopped after {consecutive_rate_limits} consecutive rate-limit responses. "
                        "Wait a while, increase the delay, or resume with a later Start at ticker # value."
                    )
                    break
            else:
                logger.exception("Failed to analyze quality/value ticker %s", ticker)
                skipped.append(SkippedTicker(ticker, "exception", str(exc)))
                consecutive_rate_limits = 0
        finally:
            progress_bar.progress((i + 1) / total)

    df = pd.DataFrame(results)
    if df.empty:
        st.write("No valid data found for the Quality vs. Value Screener.")
        return BatchAnalysisResult(None, skipped)

    # ── Percentile‑based normalization ─────────────────────────────────
    df["Quality Score"] = df["Raw ROE"].rank(pct=True)
    df["Growth Score"] = df["Raw Revenue Growth"].rank(pct=True)
    df["Stability Score"] = 1 - df["Raw Debt‑to‑Equity"].rank(pct=True)

    for col in ["Quality Score", "Growth Score", "Stability Score"]:
        df[col] = df[col].fillna(0.5)

    df["Overall Score"] = (
        VALUE_WEIGHT * df["Value Score"] +
        QUALITY_WEIGHT * df["Quality Score"] +
        GROWTH_WEIGHT * df["Growth Score"] +
        STABILITY_WEIGHT * df["Stability Score"] +
        FINANCIAL_HEALTH_WEIGHT * df["Financial Health Score"]
    )

    return BatchAnalysisResult(df.sort_values("Overall Score", ascending=False), skipped)
