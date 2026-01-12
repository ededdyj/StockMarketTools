import os
from typing import List

import pandas as pd
import streamlit as st
import yfinance as yf

from models.valuation import calculate_fair_value
from utils.fundamentals import extract_fundamentals
from config.philosophies import get_philosophy

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

def _discover_csv_paths(folder: str = "data") -> dict[str, str]:
    """Return a mapping {Pretty Name → full path} for every *_tickers.csv
    found in *folder*."""
    paths: dict[str, str] = {}
    if os.path.isdir(folder):
        for fname in os.listdir(folder):
            if fname.lower().endswith("_tickers.csv"):
                key = fname[:-12]  # strip _tickers.csv
                key = key.replace("_", " ").replace("-", " ").title()
                paths[key] = os.path.join(folder, fname)
    return paths

CSV_PATHS = _discover_csv_paths()
GARP_PHILOSOPHY = get_philosophy("Growth-at-a-Reasonable-Price")
GARP_ASSUMPTIONS = GARP_PHILOSOPHY.default_assumptions
MIN_ROE = GARP_ASSUMPTIONS.get("min_roe", 0.12)
MIN_REVENUE_GROWTH = GARP_ASSUMPTIONS.get("min_revenue_growth", 0.10)
VALUE_WEIGHT = GARP_ASSUMPTIONS.get("value_weight", 0.4)
DEFAULT_OTHER_WEIGHTS = (0.3, 0.2, 0.1)
remaining_weight = max(0.0, 1.0 - VALUE_WEIGHT)
scale = remaining_weight / sum(DEFAULT_OTHER_WEIGHTS) if sum(DEFAULT_OTHER_WEIGHTS) else 1.0
QUALITY_WEIGHT = DEFAULT_OTHER_WEIGHTS[0] * scale
GROWTH_WEIGHT = DEFAULT_OTHER_WEIGHTS[1] * scale
STABILITY_WEIGHT = DEFAULT_OTHER_WEIGHTS[2] * scale

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

# ---------------------------------------------------------------------------
# 3. Main Streamlit entry point
# ---------------------------------------------------------------------------

def analyze_quality_value_screener():
    """Run the screener and return a ranked DataFrame."""

    # ── Sidebar UI ──────────────────────────────────────────────────────
    st.sidebar.subheader("Universe")
    options = list(CSV_PATHS.keys())
    if not options:
        st.error("No *_tickers.csv files found in the data/ folder.")
        return None

    default_index = options.index("Dow 30") if "Dow 30" in options else 0
    universe = st.sidebar.selectbox("Choose a list of tickers", options, index=default_index)
    uploaded_file = st.sidebar.file_uploader("…or upload a CSV with tickers", type="csv")

    tickers = get_tickers(universe, uploaded_file)
    if not tickers:
        st.warning("No tickers found for the selected universe.")
        return None

    # ── Analysis loop ───────────────────────────────────────────────────
    results = []
    progress_bar = st.progress(0)
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            cashflow = stock.cashflow

            # Skip if we cannot price the security at all
            if current_price is None or cashflow is None or cashflow.empty:
                continue

            fundamentals = extract_fundamentals(info, stock.balance_sheet)
            valuation = calculate_fair_value(
                cashflow,
                net_debt=fundamentals.net_debt,
                shares_outstanding=fundamentals.shares_outstanding,
            )
            if valuation is None:
                continue

            fair_value = valuation.fair_value_per_share
            if fair_value and fair_value > 0:
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
                "Net Debt": fundamentals.net_debt,
                "Raw ROE": roe,
                "Raw Revenue Growth": rev_growth,
                "Raw Debt‑to‑Equity": d2e,
                "Meets ROE Target": meets_roe_target,
                "Meets Growth Target": meets_growth_target,
                "Fundamental Notes": "; ".join(fundamentals.warnings),
            })
        except Exception:
            # Silently skip problematic tickers
            pass
        finally:
            progress_bar.progress((i + 1) / total)

    df = pd.DataFrame(results)
    if df.empty:
        st.write("No valid data found for the Quality vs. Value Screener.")
        return None

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
        STABILITY_WEIGHT * df["Stability Score"]
    )

    return df.sort_values("Overall Score", ascending=False)
