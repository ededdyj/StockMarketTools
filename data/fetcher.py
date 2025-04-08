import yfinance as yf
import pandas as pd


def get_stock_data(ticker: str, timeframe: dict = None) -> dict:
    """
    Fetches stock information, historical price data, and cash flow data for a given ticker.

    Parameters:
      ticker (str): The stock ticker.
      timeframe (dict): Dictionary specifying 'period' or 'start'/'end' for historical data.

    Returns:
      dict: Contains 'info', 'history', and 'cashflow'.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if timeframe:
            if "period" in timeframe:
                history = stock.history(period=timeframe["period"])
            elif "start" in timeframe and "end" in timeframe:
                history = stock.history(start=timeframe["start"], end=timeframe["end"])
            else:
                history = stock.history(period="1y")
        else:
            history = stock.history(period="1y")

        cashflow = stock.cashflow  # Typically a DataFrame with financial periods as columns
        return {
            "info": info,
            "history": history,
            "cashflow": cashflow
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {}
