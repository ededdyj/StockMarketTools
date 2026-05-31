import yfinance as yf
import numpy as np

# Increase request timeout (adjust as needed)
yf.shared._requests_kwargs = {"timeout": 60}

import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple, Optional

from data.fetcher import get_stock_data
from data.market_inputs import get_market_inputs
from models.dcf_assumptions import DynamicDcfEstimate, estimate_dynamic_dcf_assumptions
from models.dcf_warnings import DcfWarning, generate_dcf_warnings
from models.free_cash_flow import FreeCashFlowSnapshot, resolve_free_cash_flow
from models.valuation import (
    DcfAssumptions,
    ScenarioValuation,
    ValuationResult,
    calculate_fair_value,
    calculate_fair_value_range,
    calculate_scenario_valuations,
    calculate_sensitivity_table,
    default_scenarios,
    reverse_dcf_implied_growth,
)
from models.financial_health import calculate_financial_health, FinancialHealthResult
from utils.charts import plot_price_history, plot_cashflow
from analysis.sp500_deals import analyze_sp500_deals
from analysis.quality_value_screener import analyze_quality_value_screener
from config.philosophies import get_philosophy_options, get_philosophy
from utils.logger import get_logger, read_recent_logs
from utils.fundamentals import extract_fundamentals, FundamentalsSnapshot
from utils.dividends import estimate_annual_dividend_income
from content.knowledge_map import get_knowledge_nodes
from content.research_prompt import StockResearchPromptInputs, build_stock_research_prompt

st.set_page_config(page_title="Eddy's Stocks Dashboard", layout="wide")
st.title("Eddy's Stocks - Personal Financial Dashboard")

logger = get_logger(__name__)


MODE_DESCRIPTIONS: Dict[str, str] = {
    "Single Stock Analysis": "Deep dive on one ticker with metrics, cash flow, and valuation.",
    "SP500 Deals": "Run a batch DCF to surface S&P 500 names trading below intrinsic value.",
    "Quality vs Value Screener": "Rank a universe by composite quality, growth, stability, and value scores.",
    "Knowledge Map": "Learn the assumptions, formulas, data sources, and limitations behind the app.",
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

LOG_LINES_TO_DISPLAY = 200
DEFAULT_DCF_ASSUMPTIONS = DcfAssumptions.defaults()
DCF_RATE_LIMIT = 50.0
DCF_YEARS_MIN = 1
DCF_YEARS_MAX = 20


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


def _set_dcf_session_state(assumptions: DcfAssumptions) -> None:
    st.session_state["dcf_discount_rate_pct"] = assumptions.discount_rate * 100
    st.session_state["dcf_growth_rate_pct"] = assumptions.growth_rate * 100
    st.session_state["dcf_terminal_rate_pct"] = assumptions.terminal_growth_rate * 100
    st.session_state["dcf_projection_years"] = assumptions.projection_years


def _initialize_dcf_session_state(default_assumptions: DcfAssumptions, state_key: str) -> None:
    if st.session_state.get("dcf_assumption_state_key") != state_key:
        _set_dcf_session_state(default_assumptions)
        st.session_state["dcf_assumption_state_key"] = state_key
        return

    if "dcf_discount_rate_pct" not in st.session_state:
        _set_dcf_session_state(default_assumptions)


def get_user_dcf_assumptions(
    default_assumptions: DcfAssumptions = DEFAULT_DCF_ASSUMPTIONS,
    state_key: str = "static-default",
    reset_label: str = "Reset to defaults",
) -> tuple[DcfAssumptions, bool, Optional[str]]:
    _initialize_dcf_session_state(default_assumptions, state_key)
    with st.sidebar.expander("DCF Assumptions", expanded=False):
        st.caption("Defaults may be generated from available market and company data; edit any field to stress-test your case.")
        if st.button(reset_label, key="dcf_reset"):
            _set_dcf_session_state(default_assumptions)

        st.number_input(
            "Discount Rate (%)",
            min_value=-DCF_RATE_LIMIT,
            max_value=DCF_RATE_LIMIT,
            format="%.2f",
            key="dcf_discount_rate_pct",
        )
        st.number_input(
            "Growth Rate (%)",
            min_value=-DCF_RATE_LIMIT,
            max_value=DCF_RATE_LIMIT,
            format="%.2f",
            key="dcf_growth_rate_pct",
        )
        st.number_input(
            "Terminal Growth Rate (%)",
            min_value=-DCF_RATE_LIMIT,
            max_value=DCF_RATE_LIMIT,
            format="%.2f",
            key="dcf_terminal_rate_pct",
        )
        st.number_input(
            "Projection Years",
            min_value=DCF_YEARS_MIN,
            max_value=DCF_YEARS_MAX,
            step=1,
            key="dcf_projection_years",
        )

    assumptions = DcfAssumptions(
        discount_rate=st.session_state["dcf_discount_rate_pct"] / 100.0,
        growth_rate=st.session_state["dcf_growth_rate_pct"] / 100.0,
        terminal_growth_rate=st.session_state["dcf_terminal_rate_pct"] / 100.0,
        projection_years=int(st.session_state["dcf_projection_years"]),
    )
    is_valid, message = assumptions.validate()
    return assumptions, is_valid, message


def get_user_fcf_selection(cashflow: pd.DataFrame) -> FreeCashFlowSnapshot:
    with st.sidebar.expander("DCF Starting FCF", expanded=False):
        method_label = st.selectbox(
            "Starting FCF Source",
            ["Latest fiscal year", "3-year average", "TTM fallback", "User-entered normalized FCF"],
            help="The DCF starts from this free-cash-flow value before applying growth assumptions.",
        )
        user_fcf = None
        if method_label == "User-entered normalized FCF":
            user_fcf = st.number_input(
                "Normalized FCF (USD)",
                min_value=-1_000_000_000_000.0,
                max_value=1_000_000_000_000.0,
                value=0.0,
                step=100_000_000.0,
                format="%.0f",
            )
        method_map = {
            "Latest fiscal year": "latest_fiscal_year",
            "3-year average": "three_year_average",
            "TTM fallback": "ttm",
            "User-entered normalized FCF": "user_override",
        }
    return resolve_free_cash_flow(
        cashflow,
        method=method_map[method_label],
        user_normalized_fcf=user_fcf if method_label == "User-entered normalized FCF" else None,
    )


def get_user_scenario_assumptions(base: DcfAssumptions) -> dict[str, DcfAssumptions]:
    scenarios = default_scenarios(base)
    with st.expander("Bull / Base / Bear Scenario Assumptions", expanded=False):
        st.caption("Each scenario reuses the same starting FCF, net debt, and share count; edit rates to stress-test valuation.")
        for name, defaults in list(scenarios.items()):
            cols = st.columns(3)
            with cols[0]:
                growth = st.number_input(
                    f"{name} Growth (%)",
                    value=defaults.growth_rate * 100,
                    min_value=-50.0,
                    max_value=50.0,
                    format="%.2f",
                    key=f"scenario_{name.lower()}_growth",
                ) / 100.0
            with cols[1]:
                discount = st.number_input(
                    f"{name} Discount (%)",
                    value=defaults.discount_rate * 100,
                    min_value=-50.0,
                    max_value=50.0,
                    format="%.2f",
                    key=f"scenario_{name.lower()}_discount",
                ) / 100.0
            with cols[2]:
                terminal = st.number_input(
                    f"{name} Terminal (%)",
                    value=defaults.terminal_growth_rate * 100,
                    min_value=-50.0,
                    max_value=50.0,
                    format="%.2f",
                    key=f"scenario_{name.lower()}_terminal",
                ) / 100.0
            scenarios[name] = DcfAssumptions(
                discount_rate=discount,
                growth_rate=growth,
                terminal_growth_rate=terminal,
                projection_years=base.projection_years,
            )
    return scenarios


def load_stock_bundle(ticker: str, timeframe_option: str) -> Tuple[Dict, str]:
    """Fetch ticker data with cache fallback and return (data, timeframe_note)."""

    timeframe_kwargs, timeframe_note, _ = resolve_timeframe(timeframe_option)
    timeframe_items = _normalize_timeframe_kwargs(timeframe_kwargs)
    logger.info("Loading %s with timeframe %s", ticker, timeframe_option)

    try:
        data = _load_stock_bundle_cached(ticker, timeframe_items)
    except Exception as exc:
        st.warning(
            f"Cached data retrieval failed for {ticker} ({exc}). Retrying without cache."
        )
        logger.warning("Cache load failed for %s: %s", ticker, exc)
        data = None

    if not _data_is_complete(data):
        st.warning(
            f"Yahoo Finance returned incomplete data for {ticker}. Requesting a fresh"
            " pull without cache so you see the latest available information."
        )
        logger.info("Cache miss or incomplete data for %s — refreshing directly from Yahoo", ticker)
        try:
            data = get_stock_data(ticker, timeframe=timeframe_kwargs)
        except Exception as inner_exc:
            st.error(
                f"Failed to load Yahoo Finance data for {ticker}: {inner_exc}."
                " Please try again shortly."
            )
            logger.error("Direct fetch failed for %s: %s", ticker, inner_exc)
            return {}, timeframe_note

        if not _data_is_complete(data):
            logger.warning(
                "%s still lacks usable data after refresh. Attempting fallback timeframe.",
                ticker,
            )
            fallback_kwargs = {"period": "1y"}
            try:
                fallback_data = get_stock_data(ticker, timeframe=fallback_kwargs)
            except Exception as fallback_exc:
                logger.error("Fallback fetch failed for %s: %s", ticker, fallback_exc)
                st.error(
                    f"Yahoo Finance failed to provide data for {ticker}: {fallback_exc}."
                    " Please try again shortly."
                )
                return {}, timeframe_note

            if _data_is_complete(fallback_data):
                st.info(
                    f"Price charts for {ticker} use a trailing 1-year fallback because the"
                    " requested window lacked usable price data. Fundamentals continue to"
                    " rely on the latest filings from Yahoo Finance."
                )
                logger.info("Using fallback timeframe for %s", ticker)
                return fallback_data, "Fallback to trailing twelve months."

            st.error(
                f"Yahoo Finance is missing both fundamentals and price history for {ticker}."
                " Try another ticker or different timeframe."
            )
            logger.error("Yahoo returned empty data for %s even after refresh", ticker)
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
        logger.warning("%s missing sections: %s", ticker, readable)


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


def order_modes(philosophy_name: str) -> List[str]:
    philosophy = get_philosophy(philosophy_name)
    preferred = [mode for mode in MODE_DESCRIPTIONS if mode in philosophy.tools]
    remaining = [mode for mode in MODE_DESCRIPTIONS if mode not in preferred]
    return preferred + remaining if preferred else list(MODE_DESCRIPTIONS.keys())


def format_assumption_value(value) -> str:
    if isinstance(value, (int, float)) and value != 0 and abs(value) < 1:
        return f"{value * 100:.2f}%"
    return f"{value}"


def format_dynamic_assumption_value(value, assumption: str) -> str:
    if isinstance(value, float) and assumption not in {"Beta"}:
        return format_percent(value, 2)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


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

        est_dividend = estimate_annual_dividend_income(
            10_000,
            dividend_yield=dividend_yield,
            dividend_rate=dividend_rate,
            current_price=current_price,
        )

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


def _format_signal_value(value) -> str:
    if value is None or _is_nan(value):
        return "N/A"
    value = float(value)
    if abs(value) < 10:
        return f"{value:.4f}"
    return f"{value:,.0f}"


def render_financial_health_section(
    result: FinancialHealthResult,
    source_note: str = "Yahoo Finance",
    source_warnings: Optional[List[str]] = None,
):
    st.subheader("Financial Health Score")
    st.caption(
        "Piotroski-style 0-9 score. Each signal earns 1 point when it passes; "
        "missing Yahoo Finance statement fields are shown as N/A."
    )

    col_score, col_available, col_ratio = st.columns(3)
    with col_score:
        st.metric("Financial Health Score", f"{result.score}/{result.max_score}")
    with col_available:
        st.metric("Signals Available", f"{result.available_signals}/{result.max_score}")
    with col_ratio:
        st.metric("Score Ratio", format_percent(result.score_ratio, 1))

    rows = []
    for signal in result.signals:
        if signal.passed is None:
            outcome = "N/A"
        elif signal.passed:
            outcome = "Pass"
        else:
            outcome = "Fail"
        rows.append(
            {
                "Category": signal.category,
                "Signal": signal.name,
                "Formula": signal.formula,
                "Outcome": outcome,
                "Point": signal.points,
                "Source": source_note if signal.passed is not None else "Unavailable",
                "Latest": _format_signal_value(signal.latest_value),
                "Comparison": _format_signal_value(signal.previous_value),
                "Note": signal.note,
            }
        )

    with st.expander("How the Financial Health Score is Calculated", expanded=True):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Statement data source: {source_note}.")
        if source_warnings:
            st.info("\n".join(source_warnings))
        if result.warnings:
            st.warning("\n".join(result.warnings))


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


def _warning_icon(severity: str) -> str:
    if severity == "High":
        return "High"
    if severity == "Medium":
        return "Medium"
    if severity == "Low":
        return "Low"
    return "Info"


def render_dcf_warnings(warnings: list[DcfWarning]):
    if not warnings:
        return
    high = [warning for warning in warnings if warning.severity == "High"]
    if high:
        st.warning("\n".join(f"{warning.category}: {warning.message}" for warning in high))
    with st.expander("DCF Data-Quality Warnings", expanded=bool(high)):
        rows = [
            {
                "Severity": _warning_icon(warning.severity),
                "Category": warning.category,
                "Message": warning.message,
            }
            for warning in warnings
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_equity_bridge(valuation: ValuationResult, fundamentals: FundamentalsSnapshot):
    projected_rows = [
        {
            "Year": index,
            "Projected FCF": format_currency(value, 0),
            "Formula": "Prior year FCF x (1 + explicit growth rate)",
        }
        for index, value in enumerate(valuation.projected_fcf, start=1)
    ]
    with st.expander("DCF Equity Bridge", expanded=True):
        st.markdown(
            """
**Core formulas**

- Free cash flow = Operating cash flow - capital expenditures
- In yfinance, capital expenditures are often reported as a negative cash-flow line; the app treats capex as a cash outflow and subtracts `abs(capex)` to avoid adding it by mistake.
- Net debt = total debt - cash and equivalents
- Equity value = enterprise value - net debt
- Fair value per share = equity value / shares used
"""
        )
        bridge_rows = [
            ("Starting FCF", valuation.starting_fcf, "Resolved normalized FCF", 0),
            ("PV of Explicit FCF", valuation.pv_explicit_fcf, "Sum of discounted projected FCF years", 0),
            ("Terminal Value", valuation.terminal_value, "FCF_n x (1 + terminal growth) / (discount - terminal growth)", 0),
            ("PV of Terminal Value", valuation.pv_terminal_value, "Terminal value discounted to today", 0),
            ("Enterprise Value", valuation.enterprise_value, "PV explicit FCF + PV terminal value", 0),
            ("Cash and Equivalents", fundamentals.cash_and_equivalents, fundamentals.cash_source or "Missing, assumed 0", 0),
            ("Short-Term Debt", fundamentals.short_term_debt, "Balance sheet short/current debt where available", 0),
            ("Long-Term Debt", fundamentals.long_term_debt, "Balance sheet long-term debt where available", 0),
            ("Total Debt", fundamentals.total_debt, fundamentals.debt_source or "Missing, assumed 0", 0),
            ("Net Debt", fundamentals.net_debt, "Total debt - cash and equivalents", 0),
            ("Equity Value", valuation.equity_value, "Enterprise value - net debt", 0),
            ("Shares Used", valuation.shares_used, fundamentals.shares_source or "Unavailable", 0),
            ("Fair Value per Share", valuation.fair_value_per_share, "Equity value / shares used", 2),
        ]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Bridge Item": label,
                        "Value": format_currency(value, precision) if label != "Shares Used" else format_int(value),
                        "Source / Formula": formula,
                    }
                    for label, value, formula, precision in bridge_rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        if projected_rows:
            st.markdown("**Projected FCF by Year**")
            st.dataframe(pd.DataFrame(projected_rows), use_container_width=True, hide_index=True)


def render_share_diagnostics(fundamentals: FundamentalsSnapshot):
    resolution = fundamentals.share_resolution
    if not resolution:
        return
    with st.expander("Share Count Diagnostics", expanded=resolution.data_quality_risk):
        col_selected, col_implied, col_diff = st.columns(3)
        with col_selected:
            st.metric("Shares Used", format_int(resolution.selected_shares))
            st.caption(resolution.selected_shares_source or "Unavailable")
        with col_implied:
            st.metric("Implied Shares", format_int(resolution.implied_shares_from_market_cap))
            st.caption("market cap / current price")
        with col_diff:
            st.metric("Selected vs Implied", format_percent(resolution.selected_vs_implied_pct_diff, 1))
            st.caption("Absolute percent difference")
        candidate_rows = [
            {
                "Candidate": candidate.source,
                "Shares": format_int(candidate.value),
                "Date / Period": candidate.date_or_period or "N/A",
                "Formula": candidate.formula,
            }
            for candidate in resolution.candidates
        ]
        st.dataframe(pd.DataFrame(candidate_rows), use_container_width=True, hide_index=True)
        if resolution.warnings:
            st.warning("\n".join(resolution.warnings))


def render_scenario_section(scenarios: list[ScenarioValuation]):
    st.subheader("Bull / Base / Bear DCF Scenarios")
    rows = []
    for scenario in scenarios:
        valuation = scenario.valuation
        rows.append(
            {
                "Scenario": scenario.name,
                "Starting FCF": format_currency(valuation.starting_fcf, 0) if valuation else "N/A",
                "Growth": format_percent(scenario.assumptions.growth_rate, 1),
                "Discount": format_percent(scenario.assumptions.discount_rate, 1),
                "Terminal Growth": format_percent(scenario.assumptions.terminal_growth_rate, 1),
                "Net Debt": format_currency(valuation.net_debt, 0) if valuation else "N/A",
                "Shares Used": format_int(valuation.shares_used) if valuation else "N/A",
                "Fair Value / Share": format_currency(valuation.fair_value_per_share) if valuation else "N/A",
                "Upside / Downside": format_percent(scenario.upside_downside, 1),
                "Warnings": " | ".join(scenario.warnings),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_sensitivity_section(sensitivity: pd.DataFrame):
    st.subheader("DCF Sensitivity")
    st.caption("Rows vary terminal growth; columns vary discount rate. Invalid/too-close combinations are blank.")
    if sensitivity.empty:
        st.write("Sensitivity table unavailable.")
        return
    formatted = sensitivity.copy()
    formatted["Terminal Growth"] = formatted["Terminal Growth"].apply(lambda value: format_percent(value, 1))
    for column in formatted.columns:
        if column == "Terminal Growth":
            continue
        formatted[column] = formatted[column].apply(lambda value: format_currency(value) if pd.notna(value) else "Invalid")
    formatted.columns = [
        column if column == "Terminal Growth" else f"Discount {format_percent(column, 1)}"
        for column in formatted.columns
    ]
    st.dataframe(formatted, use_container_width=True, hide_index=True)


def render_source_metadata(
    info: Dict,
    fundamentals: FundamentalsSnapshot,
    fcf_snapshot: FreeCashFlowSnapshot,
    dynamic_estimate: Optional[DynamicDcfEstimate],
):
    metadata_rows = [
        ("Current Price", info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"), "Yahoo Finance profile/history", "Latest market snapshot", "currentPrice / regularMarketPrice / previousClose"),
        ("Market Cap", info.get("marketCap"), "Yahoo Finance profile", "Latest market snapshot", "marketCap"),
        ("Shares Used", fundamentals.shares_outstanding, fundamentals.shares_source or "Unavailable", fundamentals.shares_date_or_period or "N/A", "Share-count resolver"),
        ("Implied Shares", fundamentals.implied_shares_from_market_cap, "Computed", "Latest market snapshot", "marketCap / currentPrice"),
        ("Cash and Equivalents", fundamentals.cash_and_equivalents, fundamentals.cash_source or "Fallback", fundamentals.balance_sheet_as_of or "N/A", "Latest balance-sheet cash field"),
        ("Short-Term Debt", fundamentals.short_term_debt, "Yahoo Finance balance sheet", fundamentals.balance_sheet_as_of or "N/A", "Short/current debt field"),
        ("Long-Term Debt", fundamentals.long_term_debt, "Yahoo Finance balance sheet", fundamentals.balance_sheet_as_of or "N/A", "Long-term debt field"),
        ("Total Debt", fundamentals.total_debt, fundamentals.debt_source or "Fallback", fundamentals.balance_sheet_as_of or "N/A", "Total Debt or Short + Long Debt"),
        ("Net Debt", fundamentals.net_debt, "Computed", fundamentals.balance_sheet_as_of or "N/A", "Total debt - cash and equivalents"),
        ("Operating Cash Flow", fcf_snapshot.operating_cash_flow, fcf_snapshot.source, fcf_snapshot.period or "N/A", "Cash flow statement operating cash flow"),
        ("Capital Expenditures", fcf_snapshot.capital_expenditures, fcf_snapshot.source, fcf_snapshot.period or "N/A", "Capex treated as positive outflow"),
        ("Free Cash Flow", fcf_snapshot.value, fcf_snapshot.source, fcf_snapshot.period or "N/A", fcf_snapshot.formula),
        ("Revenue", info.get("totalRevenue"), "Yahoo Finance profile", "TTM/profile field", "totalRevenue"),
        ("Beta", info.get("beta"), "Yahoo Finance profile", "Latest profile field", "beta"),
    ]
    if dynamic_estimate:
        for line in dynamic_estimate.lines:
            if line.assumption in {
                "Risk-free rate",
                "Equity risk premium",
                "Pretax cost of debt",
                "Tax rate",
                "Discount rate",
                "Growth rate",
                "Terminal growth",
            }:
                metadata_rows.append((line.assumption, line.value, line.source, "Latest available", line.formula))

    rows = [
        {
            "Input": name,
            "Value": str(format_currency(value, 0) if isinstance(value, (int, float)) and abs(value) > 10 else format_ratio(value)),
            "Source": source,
            "Date / Period": period,
            "Formula / Derivation": formula,
        }
        for name, value, source, period, formula in metadata_rows
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_dcf_section(
    info: Dict,
    cashflow: pd.DataFrame,
    fundamentals: FundamentalsSnapshot,
    philosophy,
    assumptions: DcfAssumptions,
    default_assumptions: DcfAssumptions,
    valuation: Optional[ValuationResult],
    fair_value_range,
    fcf_snapshot: FreeCashFlowSnapshot,
    dcf_warnings: list[DcfWarning],
    scenarios: list[ScenarioValuation],
    sensitivity: pd.DataFrame,
    reverse_dcf,
    dynamic_estimate: Optional[DynamicDcfEstimate] = None,
):
    st.subheader("Intrinsic Value (DCF Model)")
    if valuation is None:
        st.write("Fair Value calculation could not be completed due to missing or invalid DCF inputs.")
        render_dcf_warnings(dcf_warnings)
        return

    render_dcf_warnings(dcf_warnings)

    cards = [
        ("Enterprise Value (EV)", valuation.enterprise_value, 0),
        ("Net Debt", fundamentals.net_debt, 0),
        ("Equity Value (EV - Net Debt)", valuation.equity_value, 0),
        ("Fair Value per Share", valuation.fair_value_per_share, 2),
    ]
    cols = st.columns(len(cards))
    for col, (label, value, precision) in zip(cols, cards):
        with col:
            st.metric(label, format_currency(value, precision))

    if fair_value_range:
        st.caption(
            f"Fair Value Confidence Interval: {format_currency(fair_value_range[0])} - {format_currency(fair_value_range[1])}"
        )
    elif valuation.fair_value_per_share is None:
        st.info("Per-share valuation requires a reliable share count; Yahoo Finance did not supply one.")

    render_equity_bridge(valuation, fundamentals)
    render_share_diagnostics(fundamentals)
    render_scenario_section(scenarios)
    render_sensitivity_section(sensitivity)
    st.subheader("Reverse DCF")
    st.write(reverse_dcf.message)

    assumption_rows = [
        (
            "Discount Rate",
            format_percent(assumptions.discount_rate, 1),
            format_percent(default_assumptions.discount_rate, 1),
            "Yes" if assumptions.discount_rate != default_assumptions.discount_rate else "No",
            "Cost of capital",
        ),
        (
            "Growth Rate",
            format_percent(assumptions.growth_rate, 1),
            format_percent(default_assumptions.growth_rate, 1),
            "Yes" if assumptions.growth_rate != default_assumptions.growth_rate else "No",
            "Years 1-5 FCF growth",
        ),
        (
            "Terminal Growth",
            format_percent(assumptions.terminal_growth_rate, 1),
            format_percent(default_assumptions.terminal_growth_rate, 1),
            "Yes" if assumptions.terminal_growth_rate != default_assumptions.terminal_growth_rate else "No",
            "Perpetual growth",
        ),
        (
            "Projection Years",
            str(assumptions.projection_years),
            str(default_assumptions.projection_years),
            "Yes" if assumptions.projection_years != default_assumptions.projection_years else "No",
            "Explicit forecast horizon",
        ),
    ]
    assumption_df = pd.DataFrame(
        assumption_rows,
        columns=["Assumption", "Value", "Default", "Changed?", "Notes"],
    )

    with st.expander("Assumptions & Data"):
        st.table(assumption_df)
        st.markdown("**Source Metadata for Major Valuation Inputs**")
        render_source_metadata(info, fundamentals, fcf_snapshot, dynamic_estimate)
        if dynamic_estimate:
            dynamic_rows = [
                {
                    "Assumption": line.assumption,
                    "Suggested Value": format_dynamic_assumption_value(line.value, line.assumption),
                    "Source": line.source,
                    "Formula": line.formula,
                    "Note": line.note,
                }
                for line in dynamic_estimate.lines
            ]
            st.markdown("**Dynamic Default Derivation**")
            st.dataframe(pd.DataFrame(dynamic_rows), use_container_width=True, hide_index=True)
            if dynamic_estimate.warnings:
                st.info("\n".join(dynamic_estimate.warnings))
        st.markdown(
            f"- **Net debt source:** {fundamentals.debt_source or 'missing'}"
            f" | Cash & Equivalents: {fundamentals.cash_source or 'missing'}"
            f" | Net Debt: {format_currency(fundamentals.net_debt, 0)}"
        )
        st.markdown(
            f"- **Shares used:** {fundamentals.shares_source or 'Unavailable'}"
            f" ({format_int(fundamentals.shares_outstanding) if fundamentals.shares_outstanding else 'N/A'})"
        )
        st.markdown("- **Data source:** Yahoo Finance via yfinance")
        st.markdown(
            f"- **Balance sheet as of:** {fundamentals.balance_sheet_as_of or 'N/A'}"
            f" | **Pulled at:** {fundamentals.pulled_at}"
        )
        if assumptions != default_assumptions:
            st.caption("DCF assumptions differ from the defaults shown above.")

    st.caption("DCF outputs are scenario-based; adjust assumptions to reflect your investment case.")


def render_chatgpt_prompt_export(
    ticker: str,
    info: Dict,
    fundamentals: FundamentalsSnapshot,
    financial_health: FinancialHealthResult,
    assumptions: Optional[DcfAssumptions],
    default_assumptions: Optional[DcfAssumptions],
    dynamic_estimate: Optional[DynamicDcfEstimate],
    valuation,
    fair_value_range,
    fcf_snapshot: Optional[FreeCashFlowSnapshot],
    dcf_warnings: list[DcfWarning],
    scenarios: list[ScenarioValuation],
    sensitivity: pd.DataFrame,
    reverse_dcf,
    timeframe_option: str,
    timeframe_note: str,
):
    with st.expander("ChatGPT Research Prompt Export", expanded=False):
        st.caption(
            "Copy or download this prompt to ask ChatGPT to research the stock using the app's "
            "current output as structured starting context."
        )
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        prompt = build_stock_research_prompt(
            StockResearchPromptInputs(
                ticker=ticker,
                company_name=info.get("longName") or info.get("shortName") or ticker,
                sector=info.get("sector", "N/A"),
                industry=info.get("industry", "N/A"),
                business_summary=info.get("longBusinessSummary", ""),
                current_price=current_price,
                market_cap=info.get("marketCap"),
                enterprise_value=info.get("enterpriseValue"),
                trailing_pe=info.get("trailingPE"),
                forward_pe=info.get("forwardPE"),
                price_to_book=info.get("priceToBook"),
                profit_margins=info.get("profitMargins"),
                beta=info.get("beta"),
                dividend_yield=info.get("dividendYield"),
                payout_ratio=info.get("payoutRatio"),
                fundamentals=fundamentals,
                financial_health=financial_health,
                assumptions=assumptions,
                default_assumptions=default_assumptions,
                dynamic_estimate=dynamic_estimate,
                valuation=valuation,
                fair_value_range=fair_value_range,
                fcf_snapshot=fcf_snapshot,
                dcf_warnings=dcf_warnings,
                scenarios=scenarios,
                sensitivity_table=sensitivity,
                reverse_dcf=reverse_dcf,
                timeframe_label=timeframe_option,
                timeframe_note=timeframe_note,
            )
        )

        st.text_area(
            "Copyable prompt",
            value=prompt,
            height=520,
            help="Paste this into ChatGPT when you want a fuller research memo using current external sources.",
        )
        st.download_button(
            "Download Prompt",
            data=prompt,
            file_name=f"{ticker.lower()}_chatgpt_research_prompt.md",
            mime="text/markdown",
        )


def render_raw_data(info: Dict):
    with st.expander("Raw Data (from yfinance)"):
        st.json(info)


def render_log_panel():
    with st.expander("Application Logs (recent)"):
        log_text = read_recent_logs(LOG_LINES_TO_DISPLAY)
        st.text(log_text)


def render_knowledge_map():
    st.subheader("Knowledge Map")
    st.caption(
        "A living reference for the finance concepts, formulas, data sources, and limitations behind the app."
    )

    nodes = get_knowledge_nodes()
    categories = ["All"] + sorted({node.category for node in nodes})
    selected_category = st.selectbox("Filter by category", categories)
    visible_nodes = [
        node for node in nodes
        if selected_category == "All" or node.category == selected_category
    ]

    overview_rows = [
        {
            "Topic": node.title,
            "Category": node.category,
            "Summary": node.summary,
        }
        for node in visible_nodes
    ]
    st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

    for node in visible_nodes:
        with st.expander(f"{node.category}: {node.title}", expanded=False):
            st.markdown(f"**What it does:** {node.summary}")
            st.markdown(f"**Why it matters:** {node.why_it_matters}")

            col_inputs, col_calcs = st.columns(2)
            with col_inputs:
                st.markdown("**Inputs**")
                st.markdown("\n".join(f"- {item}" for item in node.inputs))
            with col_calcs:
                st.markdown("**Calculations / Logic**")
                st.markdown("\n".join(f"- {item}" for item in node.calculations))

            col_surfaces, col_limits = st.columns(2)
            with col_surfaces:
                st.markdown("**Where You Can Inspect It**")
                st.markdown("\n".join(f"- {item}" for item in node.transparency_surfaces))
            with col_limits:
                st.markdown("**Limitations**")
                st.markdown("\n".join(f"- {item}" for item in node.limitations))

            if node.sources:
                st.markdown("**Learn More**")
                source_rows = [
                    {
                        "Source": source.title,
                        "Why useful": source.note,
                        "Link": source.url,
                    }
                    for source in node.sources
                ]
                st.dataframe(
                    pd.DataFrame(source_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Link": st.column_config.LinkColumn("Link")},
                )


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
    financials = data.get("financials", pd.DataFrame())
    cashflow = data.get("cashflow", pd.DataFrame())
    balance_sheet = data.get("balance_sheet")
    financial_health_source = data.get("financial_health_source", "Yahoo Finance")
    sec_warnings = data.get("sec_warnings", [])

    fundamentals = extract_fundamentals(info, balance_sheet, financials=financials)
    financial_health = calculate_financial_health(financials, balance_sheet, cashflow)
    dynamic_dcf = estimate_dynamic_dcf_assumptions(
        info,
        financials,
        balance_sheet,
        cashflow,
        get_market_inputs(),
    )
    user_assumptions, assumptions_valid, assumption_error = get_user_dcf_assumptions(
        dynamic_dcf.assumptions,
        state_key=f"single-stock:{ticker}",
        reset_label="Reset to dynamic defaults",
    )
    fcf_snapshot = get_user_fcf_selection(cashflow)

    warn_if_data_missing(info, history, cashflow, ticker)

    st.subheader(f"Stock Information: {ticker}")
    if info:
        render_company_profile(info)
        render_key_financial_metrics(info)
        render_dividend_section(info, philosophy.name)
        render_governance_section(info)
    else:
        st.info("Company fundamentals are unavailable for this ticker from Yahoo Finance.")
    render_financial_health_section(financial_health, financial_health_source, sec_warnings)
    render_price_section(history, info, timeframe_option, timeframe_note)
    render_cashflow_section(cashflow)
    if assumptions_valid:
        prompt_valuation = None
        prompt_fair_value_range = None
        scenarios = []
        sensitivity = pd.DataFrame()
        reverse_dcf = reverse_dcf_implied_growth(
            None,
            None,
            None,
            None,
            user_assumptions.discount_rate,
            user_assumptions.terminal_growth_rate,
            user_assumptions.projection_years,
        )
        if fcf_snapshot.value is not None:
            prompt_valuation = calculate_fair_value(
                cashflow,
                net_debt=fundamentals.net_debt,
                shares_outstanding=fundamentals.shares_outstanding,
                assumptions=user_assumptions,
                starting_fcf=fcf_snapshot.value,
            )
            prompt_fair_value_range = calculate_fair_value_range(
                cashflow,
                net_debt=fundamentals.net_debt,
                shares_outstanding=fundamentals.shares_outstanding,
                assumptions=user_assumptions,
                starting_fcf=fcf_snapshot.value,
            )
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            scenario_assumptions = get_user_scenario_assumptions(user_assumptions)
            scenarios = calculate_scenario_valuations(
                fcf_snapshot.value,
                fundamentals.net_debt,
                fundamentals.shares_outstanding,
                current_price,
                scenario_assumptions,
            )
            sensitivity = calculate_sensitivity_table(
                fcf_snapshot.value,
                fundamentals.net_debt,
                fundamentals.shares_outstanding,
                user_assumptions,
            )
            reverse_dcf = reverse_dcf_implied_growth(
                current_price,
                fundamentals.shares_outstanding,
                fundamentals.net_debt,
                fcf_snapshot.value,
                user_assumptions.discount_rate,
                user_assumptions.terminal_growth_rate,
                user_assumptions.projection_years,
            )
        dcf_warnings = generate_dcf_warnings(
            info,
            fundamentals,
            user_assumptions,
            fcf_snapshot,
            dynamic_estimate=dynamic_dcf,
            financials=financials,
            cashflow=cashflow,
            sec_warnings=sec_warnings,
            philosophy_name=philosophy.name,
        )
        render_dcf_section(
            info,
            cashflow,
            fundamentals,
            philosophy,
            user_assumptions,
            dynamic_dcf.assumptions,
            prompt_valuation,
            prompt_fair_value_range,
            fcf_snapshot,
            dcf_warnings,
            scenarios,
            sensitivity,
            reverse_dcf,
            dynamic_estimate=dynamic_dcf,
        )
        render_chatgpt_prompt_export(
            ticker,
            info,
            fundamentals,
            financial_health,
            user_assumptions,
            dynamic_dcf.assumptions,
            dynamic_dcf,
            prompt_valuation,
            prompt_fair_value_range,
            fcf_snapshot,
            dcf_warnings,
            scenarios,
            sensitivity,
            reverse_dcf,
            timeframe_option,
            timeframe_note,
        )
    else:
        st.error(f"DCF assumptions invalid: {assumption_error}")
    if fundamentals.warnings:
        st.warning("\n".join(fundamentals.warnings))
    render_raw_data(info)


def render_sp500_deals(philosophy_name: str, mode_description: str):
    st.subheader(f"S&P 500 Deals Analysis — {philosophy_name}")
    st.caption(mode_description)
    user_assumptions, assumptions_valid, assumption_error = get_user_dcf_assumptions()
    if not assumptions_valid:
        st.error(f"DCF assumptions invalid: {assumption_error}")
        return
    st.markdown("""
Fair value is estimated using a simplified DCF model that:

- Pulls the most recent Free Cash Flow.
- Projects cash flow using the DCF assumptions in the sidebar.
- Applies the sidebar terminal growth and discount rates.
- Subtracts net debt (Total Debt − Cash) to convert Enterprise Value to Equity Value.
- Divides Equity Value by the share-count resolver's selected shares to arrive
  at a fair value per share.

Companies missing any of those inputs are skipped, so treat this as a
high-level triage for traditional value ideas. The Notes column flags share,
cash, debt, and other valuation-input risks surfaced during batch processing.
""")
    with st.spinner("Analyzing S&P 500 companies..."):
        sp500_result = analyze_sp500_deals(assumptions=user_assumptions)
    sp500_df = sp500_result.dataframe
    if sp500_result.skipped:
        with st.expander(f"Skipped tickers ({len(sp500_result.skipped)})"):
            st.dataframe(pd.DataFrame([skip.__dict__ for skip in sp500_result.skipped]))
    if sp500_df is not None and not sp500_df.empty:
        st.dataframe(sp500_df.reset_index(drop=True))
    else:
        st.write("No data available from the S&P 500 analysis.")


def render_quality_value_screener(philosophy_name: str, mode_description: str):
    st.subheader(f"Quality vs Value Screener — {philosophy_name}")
    st.caption(mode_description)
    user_assumptions, assumptions_valid, assumption_error = get_user_dcf_assumptions()
    if not assumptions_valid:
        st.error(f"DCF assumptions invalid: {assumption_error}")
        return
    st.markdown("""
This screener ranks stocks using a blended scoring model:

- **Value Score (35%)** — DCF discount to price.
- **Quality Score (25%)** — Return on Equity percentile.
- **Growth Score (15%)** — Revenue growth percentile.
- **Stability Score (10%)** — Inverted percentile for Debt-to-Equity.
- **Financial Health Score (15%)** — Piotroski-style score normalized to 0-1.

Upload your own ticker list or pick one of the pre-loaded universes.
Percentile ranks are calculated across the active universe only.
The financial health details column shows which accounting signals passed,
failed, or were unavailable from Yahoo Finance.
Fundamental notes flag share-count, cash, debt, and SEC fallback issues that can
affect valuation quality.
""")
    with st.spinner("Analyzing selected/uploaded stocks for quality and value..."):
        qv_result = analyze_quality_value_screener(assumptions=user_assumptions)
    qv_df = qv_result.dataframe
    if qv_result.skipped:
        with st.expander(f"Skipped tickers ({len(qv_result.skipped)})"):
            st.dataframe(pd.DataFrame([skip.__dict__ for skip in qv_result.skipped]))
    if qv_df is not None and not qv_df.empty:
        qv_df['Value Rank'] = qv_df['Value Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Quality Rank'] = qv_df['Quality Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Growth Rank'] = qv_df['Growth Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Stability Rank'] = qv_df['Stability Score'].rank(method='min', ascending=False).astype(int)
        qv_df['Financial Health Rank'] = qv_df['Financial Health Score'].rank(method='min', ascending=False).astype(int)
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
        st.subheader("Top 20 Leaders by Financial Health Score")
        st.dataframe(qv_df.sort_values(by='Financial Health Rank').head(20).reset_index(drop=True))
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
elif mode == "Knowledge Map":
    render_knowledge_map()

render_log_panel()
