import pandas as pd
import yfinance as yf
import streamlit as st
from typing import List
from models.valuation import calculate_fair_value

"""
Quality vs. Value Screener (CSV‑based)
=====================================

* Lets the user pick **S&P 500, NASDAQ‑100, or Dow 30** from a sidebar
  select‑box **or** upload their own CSV of tickers.
* Ticker lists are loaded from local CSV files that live in `data/`.
* No dynamic scraping or ETF look‑ups – fully offline except for the
  yfinance data pulls per ticker.
"""

# ---------------------------------------------------------------------------
# 1. CSV paths for each preset universe
# ---------------------------------------------------------------------------
CSV_PATHS = {
    "S&P 500": "data/sp500_tickers.csv",
    "NASDAQ‑100": "data/nasdaq100_tickers.csv",
    "Dow 30": "data/dow30_tickers.csv",
}


@st.cache_data(show_spinner=False)
def _load_tickers_from_csv(path: str) -> List[str]:
    """Return a list of unique tickers from the given CSV file."""
    df = pd.read_csv(path)
    # Try common column names, else first column
    for col in ["Symbol", "Ticker", "symbol", "ticker"]:
        if col in df.columns:
            return df[col].dropna().unique().tolist()
    return df.iloc[:, 0].dropna().unique().tolist()


@st.cache_data(show_spinner=False)
def get_tickers(universe: str, uploaded_file=None) -> List[str]:
    """Return ticker list based on user choice or uploaded CSV."""

    #  Uploaded CSV overrides preset lists
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            return df.iloc[:, 0].dropna().unique().tolist()
        except Exception as e:
            st.error(f"Could not read uploaded file: {e}")
            return []

    #  Preset CSV based on universe
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
# 2. Main Streamlit entry point
# ---------------------------------------------------------------------------

def analyze_quality_value_screener():
    """Run the screener and return a ranked DataFrame."""

    # ── Sidebar UI ──────────────────────────────────────────────────────
    st.sidebar.subheader("Universe")
    options = list(CSV_PATHS.keys())
    universe = st.sidebar.selectbox("Choose a list of tickers", options, index=options.index("Dow 30"))
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
            shares_out = info.get("sharesOutstanding")
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            cashflow = stock.cashflow

            # Skip if critical data is missing
            if not shares_out or current_price is None or cashflow is None or cashflow.empty:
                continue

            fair_value = calculate_fair_value(cashflow, shares_out)
            if fair_value is None:
                continue

            # Value score (positive only if undervalued)
            if fair_value and fair_value > 0:
                discount_pct = ((fair_value - current_price) / current_price) * 100 if current_price else 0
                value_score = max((fair_value - current_price) / fair_value, 0)
            else:
                discount_pct = None  # indicates fair value not meaningful
                value_score = 0

            # Raw metrics --------------------------------------------------
            roe = info.get("returnOnEquity")
            if roe is not None and roe > 1:
                roe /= 100.0

            rev_growth = info.get("revenueGrowth")
            if rev_growth is not None and rev_growth > 1:
                rev_growth /= 100.0

            d2e = info.get("debtToEquity")

            results.append({
                "Ticker": ticker,
                "Company": info.get("longName", ""),
                "Current Price": current_price,
                "Fair Value": fair_value,
                "Discount (%)": discount_pct,
                "Value Score": value_score,
                "Raw ROE": roe,
                "Raw Revenue Growth": rev_growth,
                "Raw Debt‑to‑Equity": d2e,
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
        0.4 * df["Value Score"] +
        0.3 * df["Quality Score"] +
        0.2 * df["Growth Score"] +
        0.1 * df["Stability Score"]
    )

    return df.sort_values("Overall Score", ascending=False)
