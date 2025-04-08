import pandas as pd
import yfinance as yf
import streamlit as st
from models.valuation import calculate_fair_value


@st.cache_data(show_spinner=False)
def get_sp500_tickers():
    """
    Load S&P 500 tickers from a CSV file.
    The CSV file should be located at data/sp500_tickers.csv and have a column named 'Symbol'.
    """
    try:
        df = pd.read_csv("data/sp500_tickers.csv")
        tickers = df["Symbol"].dropna().unique().tolist()
        return tickers
    except Exception as e:
        st.error("Error loading SP500 tickers: " + str(e))
        return []


def analyze_quality_value_screener():
    """
    For each ticker in the S&P 500, fetch data via yfinance, calculate fair value,
    and gather raw metrics for quality, growth, and stability.

    Instead of using fixed thresholds, we use dynamic, percentile-based normalization:
      - Quality Score: percentile rank of ROE (higher is better)
      - Growth Score: percentile rank of revenue growth (higher is better)
      - Stability Score: 1 minus the percentile rank of debt-to-equity (since lower is better)

    The Overall Score is then:
      Overall Score = 0.4 * Value Score + 0.3 * Quality Score + 0.2 * Growth Score + 0.1 * Stability Score
    """
    tickers = get_sp500_tickers()
    results = []
    progress_bar = st.progress(0)
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if not info or "sharesOutstanding" not in info:
                continue
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is None:
                continue
            cashflow = stock.cashflow
            if cashflow is None or cashflow.empty:
                continue
            fair_value = calculate_fair_value(cashflow, info.get("sharesOutstanding"))
            if fair_value is None:
                continue

            # Calculate value score (if fair value > current price)
            if fair_value > current_price:
                value_score = (fair_value - current_price) / fair_value
            else:
                value_score = 0

            # Retrieve raw metrics:
            roe = info.get("returnOnEquity")
            if roe is not None:
                # Convert to decimal if provided as a percentage (e.g., 30 becomes 0.30)
                if roe > 1:
                    roe = roe / 100.0
            revenue_growth = info.get("revenueGrowth")
            if revenue_growth is not None:
                if revenue_growth > 1:
                    revenue_growth = revenue_growth / 100.0
            debt_to_equity = info.get("debtToEquity")

            results.append({
                "Ticker": ticker,
                "Company": info.get("longName", ""),
                "Current Price": current_price,
                "Fair Value": fair_value,
                "Discount (%)": ((fair_value - current_price) / current_price) * 100 if current_price > 0 else 0,
                "Value Score": value_score,
                "Raw ROE": roe,
                "Raw Revenue Growth": revenue_growth,
                "Raw Debt-to-Equity": debt_to_equity
            })
        except Exception as e:
            continue
        progress_bar.progress((i + 1) / total)

    df = pd.DataFrame(results)
    if df.empty:
        st.write("No valid data found for Quality vs. Value Screener.")
        return None

    # Dynamic normalization using percentile ranks:
    # Quality: higher ROE is better
    df["Quality Score"] = df["Raw ROE"].rank(pct=True)
    # Growth: higher revenue growth is better
    df["Growth Score"] = df["Raw Revenue Growth"].rank(pct=True)
    # Stability: lower debt-to-equity is better, so invert the percentile ranking
    df["Stability Score"] = 1 - df["Raw Debt-to-Equity"].rank(pct=True)

    # Fill missing normalized scores with a default of 0.5
    df["Quality Score"] = df["Quality Score"].fillna(0.5)
    df["Growth Score"] = df["Growth Score"].fillna(0.5)
    df["Stability Score"] = df["Stability Score"].fillna(0.5)

    # Calculate the Overall Score using weighted factors:
    df["Overall Score"] = (
            0.4 * df["Value Score"] +
            0.3 * df["Quality Score"] +
            0.2 * df["Growth Score"] +
            0.1 * df["Stability Score"]
    )

    # Sort by Overall Score descending
    df = df.sort_values(by="Overall Score", ascending=False)
    return df
