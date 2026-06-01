import yfinance as yf
import pandas as pd

from data.sec_facts import add_sec_fallback_to_statements, get_sec_free_cash_flow_snapshot


def _safe_statement_frame(stock, attribute: str) -> pd.DataFrame:
    try:
        frame = getattr(stock, attribute, pd.DataFrame())
    except Exception:
        return pd.DataFrame()
    return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()

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

        financials = _safe_statement_frame(stock, "financials")
        cashflow = _safe_statement_frame(stock, "cashflow")  # Typically annual periods as columns
        quarterly_cashflow = _safe_statement_frame(stock, "quarterly_cashflow")
        ttm_cashflow = _safe_statement_frame(stock, "ttm_cashflow")
        balance_sheet = _safe_statement_frame(stock, "balance_sheet")
        sec_fcf_snapshot, sec_fcf_warnings = get_sec_free_cash_flow_snapshot(ticker)
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
            "quarterly_cashflow": quarterly_cashflow,
            "ttm_cashflow": ttm_cashflow,
            "sec_fcf_snapshot": sec_fcf_snapshot,
            "balance_sheet": balance_sheet,
            "financial_health_source": financial_health_source,
            "sec_warnings": sec_warnings + sec_fcf_warnings,
        }
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {}
