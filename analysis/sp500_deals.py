# analysis/sp500_deals.py

import numpy as np
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
from models.valuation import calculate_fair_value
from config.philosophies import get_philosophy
from utils.fundamentals import extract_fundamentals

VALUE_PHILOSOPHY = get_philosophy("Long-term Value/DCF")
DCF_ASSUMPTIONS = VALUE_PHILOSOPHY.default_assumptions
DCF_DISCOUNT_RATE = DCF_ASSUMPTIONS.get("discount_rate", 0.10)
DCF_GROWTH_RATE = DCF_ASSUMPTIONS.get("growth_rate", 0.03)
DCF_TERMINAL_GROWTH = DCF_ASSUMPTIONS.get("terminal_growth_rate", 0.02)
DCF_PROJECTION_YEARS = DCF_ASSUMPTIONS.get("projection_years", 5)

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

            if not info:
                continue

            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is None:
                continue

            cashflow = stock.cashflow
            if cashflow is None or cashflow.empty:
                continue

            fundamentals = extract_fundamentals(info, stock.balance_sheet)

            # Calculate fair value using our DCF model
            valuation = calculate_fair_value(
                cashflow,
                net_debt=fundamentals.net_debt,
                shares_outstanding=fundamentals.shares_outstanding,
                discount_rate=DCF_DISCOUNT_RATE,
                growth_rate=DCF_GROWTH_RATE,
                terminal_growth_rate=DCF_TERMINAL_GROWTH,
                projection_years=DCF_PROJECTION_YEARS,
            )
            if valuation is None:
                continue
            fair_value = valuation.fair_value_per_share

            # Calculate percentage discount (if fair value > current price, discount is positive)
            discount_pct = np.nan
            if fair_value is not None and current_price:
                discount_pct = ((fair_value - current_price) / current_price) * 100
            company_name = info.get("longName", "")
            results.append({
                "Ticker": ticker,
                "Company": company_name,
                "Current Price": current_price,
                "Fair Value": fair_value,
                "Net Debt": fundamentals.net_debt,
                "Discount (%)": discount_pct,
                "Notes": " | ".join(fundamentals.note_tags) if fundamentals.note_tags else "",
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
