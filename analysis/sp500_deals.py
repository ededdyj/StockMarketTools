import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
import streamlit as st
from models.valuation import calculate_fair_value, DcfAssumptions
from config.philosophies import get_philosophy
from utils.fundamentals import extract_fundamentals
from utils.paths import data_path
from analysis.results import BatchAnalysisResult, SkippedTicker
from data.fetcher import is_rate_limit_error
from data.quotes import stock_quote
from models.dcf_fit import needs_specialized_valuation
from models.free_cash_flow import resolve_free_cash_flow
from models.investment_review import finite_number, margin_of_safety

logger = logging.getLogger(__name__)

VALUE_PHILOSOPHY = get_philosophy("Long-term Value/DCF")
DCF_ASSUMPTIONS = VALUE_PHILOSOPHY.default_assumptions
DCF_DISCOUNT_RATE = DCF_ASSUMPTIONS.get("discount_rate", 0.10)
DCF_GROWTH_RATE = DCF_ASSUMPTIONS.get("growth_rate", 0.03)
DCF_TERMINAL_GROWTH = DCF_ASSUMPTIONS.get("terminal_growth_rate", 0.02)
DCF_PROJECTION_YEARS = DCF_ASSUMPTIONS.get("projection_years", 5)
VALUE_DCF_ASSUMPTIONS = DcfAssumptions(
    discount_rate=DCF_DISCOUNT_RATE,
    growth_rate=DCF_GROWTH_RATE,
    terminal_growth_rate=DCF_TERMINAL_GROWTH,
    projection_years=DCF_PROJECTION_YEARS,
)

@st.cache_data(show_spinner=False, ttl=3600)
def get_sp500_tickers():
    """
    Load S&P 500 tickers from a CSV file.
    The CSV file should be located at data/sp500_tickers.csv and have a column named 'Symbol'.
    """
    try:
        df = pd.read_csv(data_path("sp500_tickers.csv"))
        tickers = df["Symbol"].dropna().unique().tolist()
        return tickers
    except Exception as e:
        st.error("Error loading SP500 tickers: " + str(e))
        return []


@st.cache_data(show_spinner=False, ttl=900, max_entries=1024)
def load_screen_profile(ticker, _stock=None):
    stock = _stock if _stock is not None else yf.Ticker(ticker)
    return stock.info


@st.cache_data(show_spinner=False, ttl=3600, max_entries=1024)
def _load_annual_statements(ticker, _stock):
    return _stock.cashflow, _stock.balance_sheet, _stock.financials


@st.cache_data(show_spinner=False, ttl=3600)
def _screen_reference_data():
    universe = pd.read_csv(data_path("sp500_tickers.csv"), usecols=["Symbol", "GICS Sector", "GICS Sub-Industry"])
    events = pd.read_csv(data_path("valuation_events.csv"))
    classifications = universe.rename(columns={"GICS Sector": "sector", "GICS Sub-Industry": "industry"})
    return classifications.set_index("Symbol").to_dict("index"), events.set_index("Symbol").to_dict("index")


def analyze_sp500_deals(assumptions: DcfAssumptions = VALUE_DCF_ASSUMPTIONS) -> BatchAnalysisResult:
    """
    For each ticker in the S&P 500, fetch data via yfinance, calculate fair value,
    compare it with the current price, and return a DataFrame of results.
    """
    tickers = get_sp500_tickers()
    classifications, events = _screen_reference_data()
    results = []
    skipped = []
    progress_bar = st.progress(0)
    total = len(tickers)
    now = datetime.now(timezone.utc)
    rate_limits = 0

    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = load_screen_profile(ticker, stock)

            if not info:
                skipped.append(SkippedTicker(ticker, "missing_info"))
                continue

            if needs_specialized_valuation({**info, **classifications.get(ticker, {})}):
                skipped.append(SkippedTicker(ticker, "specialized_valuation", "Requires a different valuation method."))
                continue

            quote = stock_quote(info)
            quote_issue = quote.issue(now)
            if quote_issue:
                reason = "missing_price" if quote_issue == "Missing usable price" else "unverified_quote"
                skipped.append(SkippedTicker(ticker, reason, quote_issue))
                continue
            current_price = quote.price

            cashflow, balance_sheet, financials = _load_annual_statements(ticker, stock)
            if cashflow is None or cashflow.empty:
                skipped.append(SkippedTicker(ticker, "missing_cashflow"))
                continue

            fcf = resolve_free_cash_flow(cashflow)
            event = events.get(ticker)
            if event:
                period_end = pd.to_datetime(fcf.period, errors="coerce")
                first_full_year = date.fromisoformat(event["Effective date"]) + timedelta(days=364)
                if pd.isna(period_end) or period_end.date() < first_full_year:
                    skipped.append(SkippedTicker(ticker, "corporate_action_mismatch", event["Source"]))
                    continue
            fundamentals = extract_fundamentals(info, balance_sheet, financials=financials)

            # Calculate fair value using our DCF model
            valuation = calculate_fair_value(
                cashflow,
                net_debt=fundamentals.net_debt,
                shares_outstanding=fundamentals.shares_outstanding,
                assumptions=assumptions,
                starting_fcf=fcf.value,
            )
            if valuation is None:
                skipped.append(SkippedTicker(ticker, "valuation_failed"))
                continue
            fair_value = valuation.fair_value_per_share
            if not finite_number(fair_value):
                skipped.append(SkippedTicker(ticker, "missing_fair_value_per_share"))
                continue

            company_name = info.get("longName", "")
            results.append({
                "Ticker": ticker,
                "Company": company_name,
                "Current Price": current_price,
                "Fair Value": fair_value,
                "Net Debt": fundamentals.net_debt,
                "Upside/Downside %": (fair_value - current_price) / current_price,
                "Margin of Safety %": margin_of_safety(current_price, fair_value),
                "Quote date (UTC)": quote.date,
                "Annual FCF period": fcf.period,
                "Annual FCF": fcf.value,
                "Balance sheet date": fundamentals.balance_sheet_as_of,
                "Notes": " | ".join(fundamentals.note_tags) if fundamentals.note_tags else "",
            })
        except Exception as e:
            if is_rate_limit_error(e):
                skipped.append(SkippedTicker(ticker, "rate_limited", str(e)))
                rate_limits += 1
                if rate_limits >= 3:
                    skipped.extend(
                        SkippedTicker(symbol, "not_run_rate_limit_stop", "Yahoo Finance rate limit stopped the run.")
                        for symbol in tickers[i + 1 :]
                    )
                    break
                continue
            logger.exception("Failed to analyze S&P 500 ticker %s", ticker)
            skipped.append(SkippedTicker(ticker, "exception", str(e)))
        finally:
            progress_bar.progress((i + 1) / total)

    df = pd.DataFrame(results)
    if df.empty:
        st.write("No valid data found for SP500 analysis.")
        return BatchAnalysisResult(None, skipped)
    df = df.sort_values(by="Upside/Downside %", ascending=False)
    return BatchAnalysisResult(df, skipped)
