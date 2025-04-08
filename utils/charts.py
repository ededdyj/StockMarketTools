import plotly.express as px
import pandas as pd


def plot_price_history(history_df):
    """
    Generates an interactive line chart of the closing price over time.
    """
    # Reset index so that the date becomes a column
    df = history_df.reset_index()
    fig = px.line(df, x='Date', y='Close', title='Price History (Close Price)')
    return fig


def plot_cashflow(cashflow_df):
    """
    Generates a bar chart for Free Cash Flow over different periods.
    """
    # Transpose cashflow data to have dates as rows
    df = cashflow_df.T.reset_index()

    # Ensure the column exists; yfinance labels might vary, so adjust as needed
    if 'Free Cash Flow' in df.columns:
        fig = px.bar(df, x='index', y='Free Cash Flow', title='Free Cash Flow Over Time',
                     labels={'index': 'Period'})
        return fig
    else:
        return None
