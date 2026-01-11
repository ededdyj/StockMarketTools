import yfinance as yf
import numpy as np

# Increase request timeout (adjust as needed)
yf.shared._requests_kwargs = {"timeout": 60}

import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple

from data.fetcher import get_stock_data
from models.valuation import calculate_fair_value, calculate_fair_value_range
from utils.charts import plot_price_history, plot_cashflow
from analysis.sp500_deals import analyze_sp500_deals
from analysis.quality_value_screener import analyze_quality_value_screener
from config.philosophies import get_philosophy_options, get_philosophy

st.set_page_config(page_title="Eddy's Stocks Dashboard", layout="wide")
st.title("Eddy's Stocks - Personal Financial Dashboard")


MODE_DESCRIPTIONS: Dict[str, str] = {
    "Single Stock Analysis": "Deep dive on one ticker with metrics, cash flow, and valuation.",
    "SP500 Deals": "Run a batch DCF to surface S&P 500 names trading below intrinsic value.",
    "Quality vs Value Screener": "Rank a universe by composite quality, growth, stability, and value scores.",
}

DEFAULT_TICKERS: Dict[str, str] = {
    "Long-term Value/DCF": "AAPL",
    "Dividend/Income": "KO",
    "Growth-at-a-Reasonable-Price": "MSFT",
    "Momentum/Trend": "NVDA",
    "Index/Passive": "VOO",
}

TIMEFRAME_CHOICES: List[str] = [
    "Intraday (1D)",
    "1 Week",
    "1 Month",
    "3 Month",
    "6 Month",
    "1 Year",
    "3 Year",
    "5 Year",
    "10 Year",
]

PHILOSOPHY_TIMEFRAME_DEFAULTS: Dict[str, str] = {
    "Momentum/Trend": "3 Month",
    "Dividend/Income": "1 Year",
    "Index/Passive": "3 Year",
}


def _normalize_timeframe_kwargs(kwargs: Dict) -> Tuple[Tuple[str, object], ...]:
    """Convert timeframe kwargs into a hashable tuple for caching."""

    return tuple(sorted(kwargs.items()))


@st.cache_data(show_spinner=False, ttl=900)
def _load_stock_bundle_cached(ticker: str, timeframe_items: Tuple[Tuple[str, object], ...]) -> Dict:
    """Cached wrapper around yfinance data pulls."""

    timeframe_kwargs = dict(timeframe_items)
    return get_stock_data(ticker, timeframe=timeframe_kwargs)


def _data_is_complete(data: Dict) -> bool:
    if not data:
        return False
    info = data.get("info") or {}
    history = data.get("history", pd.DataFrame())
    return bool(info) or (history is not None and not history.empty)


def load_stock_bundle(ticker: str, timeframe_option: str) -> Tuple[Dict, str]:
    """Fetch ticker data with cache fallback and return (data, timeframe_note)."""

    timeframe_kwargs, timeframe_note, _ = resolve_timeframe(timeframe_option)
    timeframe_items = _normalize_timeframe_kwargs(timeframe_kwargs)

    try:
        data = _load_stock_bundle_cached(ticker, timeframe_items)
    except Exception as exc:
        st.warning(
            f"Cached data retrieval failed for {ticker} ({exc}). Retrying without cache."
        )
        data = None

    if not _data_is_complete(data):
        st.warning(
            f"Yahoo Finance returned incomplete data for {ticker}. Requesting a fresh"
            " pull without cache so you see the latest available information."
        )
        try:
            data = get_stock_data(ticker, timeframe=timeframe_kwargs)
        except Exception as inner_exc:
            st.error(
                f"Failed to load Yahoo Finance data for {ticker}: {inner_exc}."
                " Please try again shortly."
            )
            return {}, timeframe_note
        if not _data_is_complete(data):
            st.error(
                f"Yahoo Finance is missing both fundamentals and price history for {ticker}."
                " Try another ticker or different timeframe."
            )
            return {}, timeframe_note

    return data, timeframe_note


def warn_if_data_missing(info: Dict, history: pd.DataFrame, cashflow: pd.DataFrame, ticker: str) -> None:
    """Surface a dashboard note whenever data is incomplete."""

    missing_sections: List[str] = []
    if not info:
        missing_sections.append("company profile and valuation inputs")
    if history is None or history.empty:
        missing_sections.append("price history")
    if cashflow is None or cashflow.empty:
        missing_sections.append("cash flow statements / DCF inputs")

    if missing_sections:
        readable = ", ".join(missing_sections)
        st.warning(
            f"Yahoo Finance returned incomplete data for {ticker}: {readable}."
            " Some sections below may be empty or rely on stale assumptions."
        )


def _is_nan(value) -> bool:
    try:
        return np.isnan(value)
    except TypeError:
        return False


def format_currency(value, precision: int = 2) -> str:
    if value is None or _is_nan(value):
        return "N/A"
    return f"${float(value):,.{precision}f}"


def format_percent(value, precision: int = 2) -> str:
    if value is None or _is_nan(value):
        return "N/A"
    return f"{value * 100:.{precision}f}%"


def format_ratio(value, precision: int = 2) -> str:
    if value is None or _is_nan(value):
        return "N/A"
    return f"{float(value):,.{precision}f}"


def format_int(value) -> str:
    if value is None or _is_nan(value):
        return "N/A"
    return f"{int(value):,}"


def resolve_timeframe(option: str) -> Tuple[Dict, str, str]:
    """Return yfinance history kwargs, note, and label for the UI."""

    now = pd.Timestamp.utcnow()
    today_str = now.strftime("%Y-%m-%d")
    if option == "Intraday (1D)":
        return (
            {"period": "1d", "interval": "1m", "prepost": False},
            "Displays 1-minute ticks for the current regular session.",
            "1 trading day",
        )
    if option == "1 Week":
        start_date = (now - pd.DateOffset(days=7)).strftime("%Y-%m-%d")
        return (
            {"start": start_date, "end": today_str},
            "Shows the last five trading days; weekends and holidays are skipped.",
            "1 week (close-to-close)",
        )
    if option == "1 Month":
        return (
            {"period": "1mo"},
            "Based on the most recent month of trading data.",
            "1 month",
        )
    if option == "3 Month":
        return (
            {"period": "3mo"},
            "Captures the last quarter of trading activity.",
            "3 months",
        )
    if option == "6 Month":
        return (
            {"period": "6mo"},
            "Highlights the mid-term trend over six months.",
            "6 months",
        )
    if option == "1 Year":
        return (
            {"period": "1y"},
            "Represents the trailing twelve months.",
            "1 year",
        )
    if option == "3 Year":
        start_date = (now - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
        return (
            {"start": start_date, "end": today_str},
            "Pulled from daily closes over the last three calendar years.",
            "3 years",
        )
    if option == "5 Year":
        return (
            {"period": "5y"},
            "Long-term performance spanning five years.",
            "5 years",
        )
    if option == "10 Year":
        return (
            {"period": "10y"},
            "Decade-long history with monthly sampling when needed.",
            "10 years",
        )
    return (
        {"period": "1y"},
        "Fallback to trailing twelve months.",
        "1 year",
    )


@st.cache_data(show_spinner=False, ttl=900)
def load_stock_bundle(ticker: str, timeframe_option: str) -> Dict:
    timeframe_kwargs, _, _ = resolve_timeframe(timeframe_option)
    return get_stock_data(ticker, timeframe=timeframe_kwargs)


def order_modes(philosophy_name: str) -> List[str]:
    philosophy = get_philosophy(philosophy_name)
    preferred = [mode for mode in MODE_DESCRIPTIONS if mode in philosophy.tools]
    remaining = [mode for mode in MODE_DESCRIPTIONS if mode not in preferred]
    return preferred + remaining if preferred else list(MODE_DESCRIPTIONS.keys())


def format_assumption_value(value) -> str:
    if isinstance(value, (int, float)) and value != 0 and abs(value) < 1:
        return f"{value * 100:.2f}%"
    return f"{value}"


def render_philosophy_summary(philosophy):
    st.markdown(f"### Investment Philosophy: {philosophy.name}")
    st.write(philosophy.description)

    col_metrics, col_assumptions = st.columns([2, 1])
    with col_metrics:
        st.markdown("**Key Metrics Monitored**")
        st.markdown("\n".join([f"- {metric}" for metric in philosophy.key_metrics]))
    with col_assumptions:
        if philosophy.default_assumptions:
            assumption_df = pd.DataFrame(
                [
                    {
                        "Assumption": key.replace("_", " ").title(),
                        "Default": format_assumption_value(value),
                    }
                    for key, value in philosophy.default_assumptions.items()
                ]
            )
            st.markdown("**Default Assumptions**")
            st.table(assumption_df)

    st.info(
        f"Tools best suited for this philosophy: {', '.join(philosophy.tools)}."
        " Use these modules to stress-test the underlying thesis."
    )

    if philosophy.warnings:
        st.warning("\n".join([f"⚠️ {warning}" for warning in philosophy.warnings]))
    if philosophy.limitations:
        st.caption("\n".join([f"Limit: {limit}" for limit in philosophy.limitations]))


def render_company_profile(info: Dict):
    with st.expander("Company Profile"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Contact Information**")
            address = " ".join(filter(None, [info.get("address1"), info.get("address2")])).strip()
            st.write(f"**Address:** {address if address else 'N/A'}")
            st.write(
                f"**City/State/Zip:** {info.get('city', 'N/A')}, {info.get('state', 'N/A')} {info.get('zip', '')}"
            )
            st.write(f"**Country:** {info.get('country', 'N/A')}")
            st.write(f"**Phone:** {info.get('phone', 'N/A')}")
            st.write(f"**Website:** {info.get('website', 'N/A')}")
        with col2:
            st.markdown("**Overview**")
            st.write(f"**Company:** {info.get('longName', 'N/A')}")
            st.write(f"**Industry:** {info.get('industry', 'N/A')}")
            st.write(f"**Sector:** {info.get('sector', 'N/A')}")
            st.write(f"**Employees:** {format_int(info.get('fullTimeEmployees'))}")
        st.markdown("**Business Summary:**")
        st.write(info.get("longBusinessSummary", "N/A"))


def render_key_financial_metrics(info: Dict):
    with st.expander("Key Financial Metrics"):
        rows = [
            ("Previous Close", format_currency(info.get("previousClose")), "USD/share, prior close"),
            ("Open", format_currency(info.get("open")), "USD/share, latest session"),
            ("Day Low", format_currency(info.get("dayLow")), "USD/share, latest session"),
            ("Day High", format_currency(info.get("dayHigh")), "USD/share, latest session"),
            (
                "Regular Market Price",
                format_currency(info.get("regularMarketPrice")),
                "USD/share, delayed quote",
            ),
            ("Market Cap", format_currency(info.get("marketCap"), 0), "USD, latest close"),
            ("Enterprise Value", format_currency(info.get("enterpriseValue"), 0), "USD, includes debt"),
            ("Volume", format_int(info.get("volume")), "Shares traded today"),
            (
                "Average Volume",
                format_int(info.get("averageVolume")),
                "Shares/day (3M avg)",
            ),
            ("52W Low", format_currency(info.get("fiftyTwoWeekLow")), "USD/share, trailing 12M"),
            ("52W High", format_currency(info.get("fiftyTwoWeekHigh")), "USD/share, trailing 12M"),
            ("Trailing PE", format_ratio(info.get("trailingPE")), "x earnings"),
            ("Forward PE", format_ratio(info.get("forwardPE")), "x next FY earnings"),
            ("Price to Book", format_ratio(info.get("priceToBook")), "x"),
            ("Profit Margins", format_percent(info.get("profitMargins")), "Net margin (ttm)"),
            ("Beta", format_ratio(info.get("beta"), 2), "vs. S&P 500 (2Y)"),
        ]
        df_key = pd.DataFrame(rows, columns=["Metric", "Value", "Units/Context"])
        st.table(df_key)


def render_dividend_section(info: Dict, philosophy_name: str):
    with st.expander("Dividend & Distribution"):
        dividend_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
        dividend_yield = info.get("dividendYield")
        payout_ratio = info.get("payoutRatio")
        ex_dividend_date = info.get("exDividendDate")
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        if ex_dividend_date:
            ex_dividend_str = pd.to_datetime(ex_dividend_date, unit="s").strftime("%Y-%m-%d")
        else:
            ex_dividend_str = "N/A"

        est_dividend = None
        if dividend_yield and current_price:
            est_dividend = 10_000 * dividend_yield / current_price
        elif dividend_rate and current_price:
            est_dividend = (dividend_rate * 10_000) / current_price

        dividend_rows = [
            ("Dividend Rate", format_currency(dividend_rate), "USD/share (ttm)"),
            ("Dividend Yield", format_percent(dividend_yield), "Forward yield"),
            ("Payout Ratio", format_percent(payout_ratio), "FCF or earnings-based"),
            ("Ex-Dividend Date", ex_dividend_str, "Next eligible record date"),
            (
                "Est. Dividend on $10k",
                format_currency(est_dividend),
                "Annualized using yield inputs",
            ),
        ]
        df_dividend = pd.DataFrame(dividend_rows, columns=["Dividend Metric", "Value", "Units/Notes"])
        st.table(df_dividend)
        if "Dividend" in philosophy_name:
            st.info("Yield targets and payout safety drive this philosophy; validate dividend histories externally.")


def render_governance_section(info: Dict):
    with st.expander("Governance & Management"):
        st.markdown("**Key Company Officers:**")
        officers = info.get("companyOfficers")
        if officers:
            df_officers = pd.DataFrame(officers)
            cols = ["name", "title", "age", "totalPay"]
            df_officers = df_officers[[col for col in cols if col in df_officers.columns]]
            st.table(df_officers)
        else:
            st.write("No officer information available.")

        st.markdown("**Risk Ratings:**")
        risk = {
            "Audit Risk": info.get("auditRisk"),
            "Board Risk": info.get("boardRisk"),
            "Compensation Risk": info.get("compensationRisk"),
            "Shareholder Rights Risk": info.get("shareHolderRightsRisk"),
            "Overall Risk": info.get("overallRisk"),
        }
        risk_df = pd.DataFrame(
            [(metric, format_ratio(value, 0)) for metric, value in risk.items()],
            columns=["Risk Metric", "Score (0-10)"]
        )
        st.table(risk_df)
        st.markdown("**Investor Relations Website:**")
        st.write(info.get("irWebsite", "N/A"))


def render_price_section(history: pd.DataFrame, info: Dict, timeframe_option: str, timeframe_note: str):
    st.subheader(f"Price History ({timeframe_option})")
    st.caption(timeframe_note)

    if history is None or history.empty:
        st.write("Historical data not available.")
        return

    start_price = history["Close"].iloc[0]
    end_price = history["Close"].iloc[-1]
    pts_change = end_price - start_price
    pct_change = (pts_change / start_price) * 100 if start_price else np.nan

    pre_market_val = info.get("preMarketPrice")
    post_market_val = info.get("postMarketPrice")

    col_price, col_delta = st.columns([2, 1])
    with col_price:
        st.header(f"Current Price: {format_currency(end_price)}")
        st.caption(
            f"Pre-market: {format_currency(pre_market_val)} | Post-market: {format_currency(post_market_val)}"
        )
    with col_delta:
        st.metric(
            label=f"{timeframe_option} change (close-to-close)",
            value=f"{pts_change:+.2f} USD" if not _is_nan(pts_change) else "N/A",
            delta=f"{pct_change:+.2f}%" if not _is_nan(pct_change) else "N/A",
        )

    price_fig = plot_price_history(history)
    st.plotly_chart(price_fig, use_container_width=True)


def render_cashflow_section(cashflow: pd.DataFrame):
    st.subheader("Free Cash Flow")
    if cashflow is None or cashflow.empty:
        st.write("Cash flow data not available.")
        return
    cf_fig = plot_cashflow(cashflow)
    if cf_fig:
        st.plotly_chart(cf_fig, use_container_width=True)
    else:
        st.write("Free Cash Flow data not available.")


def render_dcf_section(info: Dict, cashflow: pd.DataFrame, philosophy):
    st.subheader("Intrinsic Value (DCF Model)")
    shares_outstanding = info.get("sharesOutstanding")
    if not shares_outstanding or cashflow is None or cashflow.empty:
        st.write("Insufficient data to calculate fair value.")
        return

    discount_rate = philosophy.default_assumptions.get("discount_rate", 0.10)
    growth_rate = philosophy.default_assumptions.get("growth_rate", 0.03)
    terminal_growth_rate = philosophy.default_assumptions.get("terminal_growth_rate", 0.02)
    projection_years = philosophy.default_assumptions.get("projection_years", 5)

    base_fair_value = calculate_fair_value(
        cashflow,
        shares_outstanding,
        discount_rate=discount_rate,
        growth_rate=growth_rate,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )
    if base_fair_value is None:
        st.write("Fair Value calculation could not be completed due to missing data.")
        return

    fair_value_range = calculate_fair_value_range(
        cashflow,
        shares_outstanding,
        discount_rate_base=discount_rate,
        growth_rate_base=growth_rate,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )

    assumption_df = pd.DataFrame(
        [
            ("Discount Rate", format_percent(discount_rate, 1), "Cost of capital"),
            ("Growth Rate", format_percent(growth_rate, 1), "Years 1-5 FCF growth"),
            ("Terminal Growth", format_percent(terminal_growth_rate, 1), "Perpetual growth"),
            ("Projection Years", projection_years, "Explicit forecast horizon"),
        ],
        columns=["Assumption", "Value", "Notes"],
    )

    st.write(f"Calculated Fair Value (Enterprise Value per Share): **{format_currency(base_fair_value)}**")
    if fair_value_range:
        st.write(
            f"Fair Value Confidence Interval: **{format_currency(fair_value_range[0])}** - **{format_currency(fair_value_range[1])}**"
        )
    st.caption("DCF outputs are scenario-based; adjust assumptions to reflect your investment case.")
    st.table(assumption_df)


def render_raw_data(info: Dict):
    with st.expander("Raw Data (from yfinance)"):
        st.json(info)


def single_stock_analysis(philosophy, mode_description: str):
    st.subheader(mode_description)
    default_ticker = DEFAULT_TICKERS.get(philosophy.name, "AAPL")
    ticker = st.sidebar.text_input("Enter Stock Ticker", value=default_ticker).strip().upper()

    default_timeframe = PHILOSOPHY_TIMEFRAME_DEFAULTS.get(philosophy.name, "1 Year")
    timeframe_index = TIMEFRAME_CHOICES.index(default_timeframe) if default_timeframe in TIMEFRAME_CHOICES else TIMEFRAME_CHOICES.index("1 Year")
    timeframe_option = st.sidebar.selectbox("Select Time Frame for Price History", TIMEFRAME_CHOICES, index=timeframe_index)

    if not ticker:
        st.info("Enter a ticker above to load company data.")
        return

    try:
        data, timeframe_note = load_stock_bundle(ticker, timeframe_option)
    except Exception as exc:
        st.error(
            f"Unexpected error while retrieving data for {ticker}: {exc}."
            " This has been logged; please try again shortly."
        )
        return
    if not data:
        return

    info = data.get("info", {})
    history = data.get("history", pd.DataFrame())
    cashflow = data.get("cashflow", pd.DataFrame())

    warn_if_data_missing(info, history, cashflow, ticker)

    st.subheader(f"Stock Information: {ticker}")
    if info:
        render_company_profile(info)
        render_key_financial_metrics(info)
        render_dividend_section(info, philosophy.name)
        render_governance_section(info)
    else:
        st.info("Company fundamentals are unavailable for this ticker from Yahoo Finance.")
    render_price_section(history, info, timeframe_option, timeframe_note)
    render_cashflow_section(cashflow)
    render_dcf_section(info, cashflow, philosophy)
    render_raw_data(info)


def render_sp500_deals(philosophy_name: str, mode_description: str):
    st.subheader(f"S&P 500 Deals Analysis — {philosophy_name}")
    st.caption(mode_description)
    st.markdown("""
Fair value is estimated using a simplified DCF model that:

- Pulls the most recent Free Cash Flow.
- Projects five years of cash flow using a 3% growth assumption.
- Applies a 2% terminal growth rate and discounts at 10%.
- Divides by shares outstanding to arrive at an enterprise value per share.

Companies missing any of those inputs are skipped, so treat this as a
high-level triage for traditional value ideas.
""")
    with st.spinner("Analyzing S&P 500 companies..."):
        sp500_df = analyze_sp500_deals()
    if sp500_df is not None and not sp500_df.empty:
        st.dataframe(sp500_df.reset_index(drop=True))
    else:
        st.write("No data available from the S&P 500 analysis.")


def render_quality_value_screener(philosophy_name: str, mode_description: str):
    st.subheader(f"Quality vs Value Screener — {philosophy_name}")
    st.caption(mode_description)
    st.markdown("""
This screener ranks stocks using a blended scoring model:

- **Value Score (40%)** — DCF discount to price.
- **Quality Score (30%)** — Return on Equity percentile.
- **Growth Score (20%)** — Revenue growth percentile.
- **Stability Score (10%)** — Inverted percentile for Debt-to-Equity.

Upload your own ticker list or pick one of the pre-loaded universes.
Percentile ranks are calculated across the active universe only.
""")
    with st.spinner("Analyzing selected/uploaded stocks for quality and value..."):
        qv_df = analyze_quality_value_screener()
    if qv_df is not None and not qv_df.empty:
        qv_df['Value Rank'] = qv_df['Value Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Quality Rank'] = qv_df['Quality Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Growth Rank'] = qv_df['Growth Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Stability Rank'] = qv_df['Stability Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Overall Rank'] = qv_df['Overall Score'].rank(method='min', ascending=False).astype(int)
        st.dataframe(qv_df.reset_index(drop=True))
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


##############################
# Sidebar Controls
##############################

philosophy_name = st.sidebar.selectbox("Investment Philosophy", get_philosophy_options())
philosophy = get_philosophy(philosophy_name)

ordered_modes = order_modes(philosophy_name)
mode = st.sidebar.radio(
    "Select Tool",
    ordered_modes,
    format_func=lambda m: f"{m} ⭐" if m in philosophy.tools else m,
)
st.sidebar.caption("⭐ Recommended for the selected philosophy.")
st.sidebar.markdown("---")

render_philosophy_summary(philosophy)

if mode == "Single Stock Analysis":
    single_stock_analysis(philosophy, MODE_DESCRIPTIONS[mode])
elif mode == "SP500 Deals":
    render_sp500_deals(philosophy.name, MODE_DESCRIPTIONS[mode])
elif mode == "Quality vs Value Screener":
    render_quality_value_screener(philosophy.name, MODE_DESCRIPTIONS[mode])
