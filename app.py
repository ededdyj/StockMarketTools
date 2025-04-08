import streamlit as st
import pandas as pd
from datetime import datetime

from data.fetcher import get_stock_data
from models.valuation import calculate_fair_value, calculate_fair_value_range
from utils.charts import plot_price_history, plot_cashflow
from analysis.sp500_deals import analyze_sp500_deals
from analysis.quality_value_screener import analyze_quality_value_screener

st.set_page_config(page_title="Eddy's Stocks Dashboard", layout="wide")
st.title("Eddy's Stocks - Personal Financial Dashboard")

# Sidebar mode selector
mode = st.sidebar.radio("Select Mode", ["Single Stock Analysis", "SP500 Deals", "Quality vs Value Screener"])

if mode == "Single Stock Analysis":
    st.sidebar.header("Stock Ticker Input")
    ticker = st.sidebar.text_input("Enter Stock Ticker", value="AAPL")

    # Sidebar for time frame selection
    timeframe_option = st.sidebar.selectbox(
        "Select Time Frame for Price History",
        ["1 Week", "1 Month", "3 Month", "6 Month", "1 Year", "3 Year", "5 Year", "10 Year"]
    )

    # Map timeframe selection to parameters for yfinance history
    if timeframe_option == "1 Week":
        start_date = (pd.Timestamp.today() - pd.DateOffset(days=7)).strftime("%Y-%m-%d")
        tf = {"start": start_date, "end": pd.Timestamp.today().strftime("%Y-%m-%d")}
        st.info("Note: The 1 Week chart displays only trading days (weekends and holidays are excluded).")
    elif timeframe_option == "1 Month":
        tf = {"period": "1mo"}
    elif timeframe_option == "3 Month":
        tf = {"period": "3mo"}
    elif timeframe_option == "6 Month":
        tf = {"period": "6mo"}
    elif timeframe_option == "1 Year":
        tf = {"period": "1y"}
    elif timeframe_option == "3 Year":
        start_date = (pd.Timestamp.today() - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
        tf = {"start": start_date, "end": pd.Timestamp.today().strftime("%Y-%m-%d")}
    elif timeframe_option == "5 Year":
        tf = {"period": "5y"}
    elif timeframe_option == "10 Year":
        tf = {"period": "10y"}
    else:
        tf = {"period": "1y"}  # Fallback option

    if ticker:
        st.subheader(f"Stock Information: {ticker.upper()}")
        data = get_stock_data(ticker, timeframe=tf)
        info = data.get("info", {})

        # Display basic company info
        if info:
            st.write("**Basic Company Info**")
            st.write(info)
        else:
            st.write("No stock information available.")

        # ---------------------
        # PRICE HISTORY + METRICS
        # ---------------------
        st.subheader(f"Price History ({timeframe_option})")
        history = data.get("history", pd.DataFrame())

        if not history.empty:
            desired_metrics = {
                "Current Price": info.get("currentPrice"),
                "Regular Market Price": info.get("regularMarketPrice"),
                "Pre-Market Price": info.get("preMarketPrice"),
                "Pre-Market Change": info.get("preMarketChange"),
                "Pre-Market Change (%)": info.get("preMarketChangePercent"),
                "Regular Market Change": info.get("regularMarketChange"),
                "Regular Market Day Range": info.get("regularMarketDayRange"),
                "Target High Price": info.get("targetHighPrice"),
                "Target Low Price": info.get("targetLowPrice"),
                "Target Mean Price": info.get("targetMeanPrice"),
                "Target Median Price": info.get("targetMedianPrice"),
            }
            # Convert values to strings to avoid type conversion issues
            desired_metrics_str = {k: (str(v) if v is not None else "N/A") for k, v in desired_metrics.items()}
            df_metrics = pd.DataFrame(desired_metrics_str, index=[0]).T.reset_index()
            df_metrics.columns = ["Metric", "Value"]
            st.table(df_metrics)

            price_fig = plot_price_history(history)
            st.plotly_chart(price_fig)
        else:
            st.write("Historical data not available.")

        # ---------------------
        # FREE CASH FLOW CHART
        # ---------------------
        st.subheader("Free Cash Flow")
        cashflow = data.get("cashflow", pd.DataFrame())
        if not cashflow.empty:
            cf_fig = plot_cashflow(cashflow)
            if cf_fig:
                st.plotly_chart(cf_fig)
            else:
                st.write("Free Cash Flow data not available.")
        else:
            st.write("Cash flow data not available.")

        # ---------------------
        # FAIR VALUE (DCF MODEL) + CONFIDENCE INTERVAL
        # ---------------------
        st.subheader("Fair Value Calculation (DCF Model)")
        shares_outstanding = info.get("sharesOutstanding", None)
        if shares_outstanding and not cashflow.empty:
            base_fair_value = calculate_fair_value(cashflow, shares_outstanding)
            fair_value_range = calculate_fair_value_range(cashflow, shares_outstanding)
            if base_fair_value:
                st.write(f"Calculated Fair Value (Enterprise Value per Share): **${base_fair_value:,.2f}**")
                if fair_value_range is not None:
                    st.write(
                        f"Fair Value Confidence Interval: **${fair_value_range[0]:,.2f}** - **${fair_value_range[1]:,.2f}**")
                else:
                    st.write("Fair Value confidence interval could not be calculated due to missing data.")
            else:
                st.write("Fair Value calculation could not be completed due to missing data.")
        else:
            st.write("Insufficient data to calculate Fair Value.")

elif mode == "SP500 Deals":
    st.subheader("S&P 500 Deals Analysis")
    st.markdown("""
    **Fair Value Calculation Explanation:**

    For each company, fair value is estimated using a simplified Discounted Cash Flow (DCF) model that:

    - **Extracts the most recent Free Cash Flow (FCF):**  
      Uses the most recent FCF value from the company's cash flow statement.

    - **Projects FCF for 5 years:**  
      Assumes an annual FCF growth rate of **3%** for the next 5 years.

    - **Calculates Terminal Value:**  
      Computes a terminal value at the end of the projection period using a terminal growth rate of **2%** and a discount rate of **10%**.

    - **Discounts to Present Value:**  
      Discounts the projected FCF and terminal value back to the present using the discount rate.

    - **Derives Fair Value per Share:**  
      Sums the present values to obtain the enterprise value and divides by the number of shares outstanding.

    **Note:** This simplified DCF model is for exploratory analysis and may not capture all complexities of a company’s valuation.
    """)

    st.write(
        "This analysis calculates the fair value for each company in the S&P 500 and compares it with the current trading price to highlight the best deals. (Companies missing necessary data are skipped.)")

    with st.spinner("Analyzing S&P 500 companies..."):
        sp500_df = analyze_sp500_deals()

    if sp500_df is not None and not sp500_df.empty:
        st.dataframe(sp500_df.reset_index(drop=True))
    else:
        st.write("No data available from the S&P 500 analysis.")

elif mode == "Quality vs Value Screener":
    st.subheader("Quality vs Value Screener")
    st.markdown("""
    **Quality vs. Value Screener Explanation:**

    This screener ranks S&P 500 stocks based on a composite score derived from:

    - **Value Score:**  
      The discount between the fair value (calculated via a simplified DCF model) and the current trading price.
      A higher discount (i.e., current price well below fair value) yields a higher value score.

    - **Quality Score:**  
      Based on Return on Equity (ROE). Raw ROE values are converted into a percentile rank so that stocks with higher ROE receive higher scores.

    - **Growth Score:**  
      Based on revenue growth, normalized by its percentile rank.

    - **Stability Score:**  
      Based on debt-to-equity. Since lower debt is preferred, we invert the percentile ranking so that companies with lower ratios score higher.

    The overall score is calculated as:

    `Overall Score = 0.4 * Value Score + 0.3 * Quality Score + 0.2 * Growth Score + 0.1 * Stability Score`

    Stocks with a higher overall score are considered better opportunities from a quality and value perspective.
    """)

    with st.spinner("Analyzing S&P 500 stocks for quality and value..."):
        qv_df = analyze_quality_value_screener()

    if qv_df is not None and not qv_df.empty:
        # Add ranking columns for each individual score
        qv_df['Value Rank'] = qv_df['Value Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Quality Rank'] = qv_df['Quality Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Growth Rank'] = qv_df['Growth Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Stability Rank'] = qv_df['Stability Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Overall Rank'] = qv_df['Overall Score'].rank(method='min', ascending=False).astype(int)

        st.dataframe(qv_df.reset_index(drop=True))

        # Separate tables for top 20 leaders in each category:
        st.subheader("Top 20 Leaders by Value Score")
        st.dataframe(qv_df.sort_values(by='Value Rank').head(20).reset_index(drop=True))

        st.subheader("Top 20 Leaders by Quality Score")
        st.dataframe(qv_df.sort_values(by='Quality Rank').head(20).reset_index(drop=True))

        st.subheader("Top 20 Leaders by Growth Score")
        st.dataframe(qv_df.sort_values(by='Growth Rank').head(20).reset_index(drop=True))

        st.subheader("Top 20 Leaders by Stability Score")
        st.dataframe(qv_df.sort_values(by='Stability Rank').head(20).reset_index(drop=True))

        st.subheader("Top 20 Leaders by Overall Score")
        st.dataframe(qv_df.sort_values(by='Overall Rank').head(20).reset_index(drop=True))
    else:
        st.write("No data available from the Quality vs. Value Screener.")

