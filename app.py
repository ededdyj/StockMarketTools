import yfinance as yf

# Increase request timeout (adjust as needed)
yf.shared._requests_kwargs = {"timeout": 60}

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

# Sidebar: Mode selector
mode = st.sidebar.radio("Select Mode", ["Single Stock Analysis", "SP500 Deals", "Quality vs Value Screener"])

########################################
# SINGLE STOCK ANALYSIS MODE
########################################
if mode == "Single Stock Analysis":
    st.sidebar.header("Stock Ticker Input")
    ticker = st.sidebar.text_input("Enter Stock Ticker", value="AAPL")

    # Add "Intraday (1D)" option along with other time frames
    timeframe_option = st.sidebar.selectbox(
        "Select Time Frame for Price History",
        ["Intraday (1D)", "1 Week", "1 Month", "3 Month", "6 Month", "1 Year", "3 Year", "5 Year", "10 Year"]
    )

    # Map timeframe selection to yfinance history parameters
    if timeframe_option == "Intraday (1D)":
        tf = {"period": "1d", "interval": "1m", "prepost": True}
        st.info("Intraday (1D) chart displaying minute-level data with extended hours enabled.")
    elif timeframe_option == "1 Week":
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

        ############# Company Profile #############
        with st.expander("Company Profile"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Contact Information**")
                address1 = info.get("address1", "")
                address2 = info.get("address2", "")
                address = f"{address1} {address2}".strip()
                st.write(f"**Address:** {address if address else 'N/A'}")
                st.write(
                    f"**City/State/Zip:** {info.get('city', 'N/A')}, {info.get('state', 'N/A')} {info.get('zip', '')}")
                st.write(f"**Country:** {info.get('country', 'N/A')}")
                st.write(f"**Phone:** {info.get('phone', 'N/A')}")
                st.write(f"**Website:** {info.get('website', 'N/A')}")
            with col2:
                st.markdown("**Overview**")
                st.write(f"**Company:** {info.get('longName', 'N/A')}")
                st.write(f"**Industry:** {info.get('industry', 'N/A')}")
                st.write(f"**Sector:** {info.get('sector', 'N/A')}")
                st.write(f"**Employees:** {info.get('fullTimeEmployees', 'N/A')}")
            st.markdown("**Business Summary:**")
            st.write(info.get("longBusinessSummary", "N/A"))

        ############# Key Financial Metrics #############
        with st.expander("Key Financial Metrics"):
            key_metrics = {
                "Previous Close": info.get("previousClose"),
                "Open": info.get("open"),
                "Day Low": info.get("dayLow"),
                "Day High": info.get("dayHigh"),
                "Regular Market Price": info.get("regularMarketPrice"),
                "Market Cap": info.get("marketCap"),
                "Volume": info.get("volume"),
                "Average Volume": info.get("averageVolume"),
                "52W Low": info.get("fiftyTwoWeekLow"),
                "52W High": info.get("fiftyTwoWeekHigh"),
                "Trailing PE": info.get("trailingPE"),
                "Forward PE": info.get("forwardPE"),
                "Price to Book": info.get("priceToBook"),
                "Enterprise Value": info.get("enterpriseValue"),
                "Profit Margins": info.get("profitMargins"),
                "Beta": info.get("beta")
            }
            df_key = pd.DataFrame(key_metrics.items(), columns=["Metric", "Value"])
            st.table(df_key)

        ############# Dividend & Distribution #############
        with st.expander("Dividend & Distribution"):
            dividend_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
            dividend_yield = info.get("dividendYield")
            ex_dividend_date = info.get("exDividendDate")
            payout_ratio = info.get("payoutRatio")
            current_price = info.get("currentPrice")

            if ex_dividend_date:
                ex_div_date_str = pd.to_datetime(ex_dividend_date, unit="s").strftime('%Y-%m-%d')
            else:
                ex_div_date_str = "N/A"

            est_dividend = None
            if dividend_yield and current_price and dividend_yield > 0 and current_price > 0:
                est_dividend = 10000 * (dividend_yield / 100)
            elif dividend_rate and current_price and current_price > 0:
                est_dividend = (dividend_rate * 10000) / current_price

            display_yield_pct = f"{dividend_yield:.2f}%" if dividend_yield is not None else "N/A"
            display_payout_ratio = f"{payout_ratio:.2f}" if payout_ratio is not None and payout_ratio < 10_000 else "N/A"

            dividend_data = {
                "Dividend Rate ($/share)": f"{dividend_rate:.2f}" if dividend_rate is not None else "N/A",
                "Dividend Yield (%)": display_yield_pct,
                "Ex-Dividend Date": ex_div_date_str,
                "Payout Ratio": display_payout_ratio,
            }
            if est_dividend:
                dividend_data["Est. Dividend per Year on $10,000"] = f"${est_dividend:,.2f}"
            else:
                dividend_data["Est. Dividend per Year on $10,000"] = "N/A"

            df_dividend = (
                pd.DataFrame(dividend_data, index=[0])
                .T.reset_index()
                .rename(columns={"index": "Dividend Metric", 0: "Value"})
            )
            df_dividend["Value"] = df_dividend["Value"].astype(str)
            st.table(df_dividend)

        ############# Governance & Management #############
        with st.expander("Governance & Management"):
            st.markdown("**Key Company Officers:**")
            if info.get("companyOfficers"):
                df_officers = pd.DataFrame(info.get("companyOfficers"))
                if not df_officers.empty:
                    cols = ["name", "title", "age", "totalPay"]
                    df_officers = df_officers[[col for col in cols if col in df_officers.columns]]
                    st.table(df_officers)
                else:
                    st.write("No officer information available.")
            else:
                st.write("No company officer information available.")

            st.markdown("**Risk Ratings:**")
            risk = {
                "Audit Risk": info.get("auditRisk"),
                "Board Risk": info.get("boardRisk"),
                "Compensation Risk": info.get("compensationRisk"),
                "Shareholder Rights Risk": info.get("shareHolderRightsRisk"),
                "Overall Risk": info.get("overallRisk")
            }
            st.table(pd.DataFrame(risk.items(), columns=["Risk Metric", "Value"]))

            st.markdown("**Investor Relations Website:**")
            st.write(info.get("irWebsite", "N/A"))

        ############# Price History & Current Price Display #############
        st.subheader(f"Price History ({timeframe_option})")
        # Display current, pre-market, and post-market prices
        current_price_val = info.get("currentPrice")
        pre_market_val = info.get("preMarketPrice", "N/A")
        post_market_val = info.get("postMarketPrice", "N/A")
        if current_price_val is not None:
            st.header(f"Current Price: ${current_price_val}")
            st.caption(f"Pre-market: ${pre_market_val} | Post-market: ${post_market_val}")
        else:
            st.write("Current price not available.")

        history = data.get("history", pd.DataFrame())
        if not history.empty:
            price_fig = plot_price_history(history)
            st.plotly_chart(price_fig)

            # Expander for raw price data debug info
            with st.expander("Raw Price Data Debug Info"):
                st.write("### DataFrame Output")
                st.write(history)
                st.write("### JSON Output")
                st.json(history.to_dict())
        else:
            st.write("Historical data not available.")

        ############# Free Cash Flow Chart #############
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

        ############# Fair Value Calculation #############
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

        ############# Raw Data #############
        with st.expander("Raw Data"):
            st.json(info)

########################################
# SP500 DEALS MODE
########################################
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

########################################
# QUALITY VS VALUE SCREENER MODE
########################################
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

        # Provide separate tables with top 20 leaders for each category:
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
