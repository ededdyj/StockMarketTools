import plotly.express as px
import pandas as pd


def plot_price_history(history_df):
    """
    Generates an interactive line chart of the closing price over time.
    Works for both daily and intraday data.
    """

    df = history_df.reset_index()

    # Use whatever the time column is called ("Date" or "Datetime")
    time_col = df.columns[0]

    fig = px.line(
        df,
        x=time_col,
        y="Close",
        title="Price History (Close Price)",
        labels={time_col: "Time", "Close": "Price"},
    )
    fig.update_xaxes(rangeslider_visible=True)
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
