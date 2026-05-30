import yfinance as yf
import pandas as pd

from data.sec_facts import add_sec_fallback_to_statements

def get_stock_data(ticker: str, timeframe: dict = None) -> dict:
    """
    Fetches stock information, historical price data (including intraday data), and cash flow data for a given ticker.

    Parameters:
      ticker (str): The stock ticker.
      timeframe (dict): A dictionary with parameters for yfinance's history() method.
                        For example:
                          {"period": "1d", "interval": "1m", "prepost": False}

    Returns:
      dict: Contains 'info' (stock information), 'history' (the price data DataFrame), and 'cashflow'.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if timeframe is None:
            history = stock.history(period="1y")
        else:
            # Pass all parameters in timeframe directly
            history = stock.history(**timeframe)

        financials = stock.financials
        cashflow = stock.cashflow  # Typically a DataFrame with financial periods as columns
        balance_sheet = stock.balance_sheet
        (
            financials,
            balance_sheet,
            cashflow,
            financial_health_source,
            sec_warnings,
        ) = add_sec_fallback_to_statements(ticker, financials, balance_sheet, cashflow)
        return {
            "info": info,
            "history": history,
            "financials": financials,
            "cashflow": cashflow,
            "balance_sheet": balance_sheet,
            "financial_health_source": financial_health_source,
            "sec_warnings": sec_warnings,
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {}
