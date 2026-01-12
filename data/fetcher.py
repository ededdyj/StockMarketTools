import yfinance as yf
import pandas as pd

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

        cashflow = stock.cashflow  # Typically a DataFrame with financial periods as columns
        balance_sheet = stock.balance_sheet
        return {
            "info": info,
            "history": history,
            "cashflow": cashflow,
            "balance_sheet": balance_sheet,
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {}
