# analysis/sp500_deals.py

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

def analyze_sp500_deals():
    """
    For each ticker in the S&P 500, fetch data via yfinance, calculate fair value,
    compare it with the current price, and return a DataFrame of results.
    """
    tickers = get_sp500_tickers()
    results = []
    progress_bar = st.progress(0)
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Ensure we have the required data
            if not info or "sharesOutstanding" not in info:
                continue

            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is None:
                continue

            cashflow = stock.cashflow
            if cashflow is None or cashflow.empty:
                continue

            # Calculate fair value using our DCF model
            fair_value = calculate_fair_value(cashflow, info.get("sharesOutstanding"))
            if fair_value is None:
                continue

            # Calculate percentage discount (if fair value > current price, discount is positive)
            discount_pct = ((fair_value - current_price) / current_price) * 100
            company_name = info.get("longName", "")
            results.append({
                "Ticker": ticker,
                "Company": company_name,
                "Current Price": current_price,
                "Fair Value": fair_value,
                "Discount (%)": discount_pct
            })
        except Exception as e:
            # Skip problematic tickers
            continue
        progress_bar.progress((i + 1) / total)

    df = pd.DataFrame(results)
    if df.empty:
        st.write("No valid data found for SP500 analysis.")
        return None
    # Sort by Discount (%) descending (i.e. best deals first)
    df = df.sort_values(by="Discount (%)", ascending=False)
    return df
