"""Streamlit review editor and saved watchlist."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
import sqlite3

import pandas as pd
import streamlit as st

from analysis.sp500_deals import load_screen_profile
from content.review_examples import worked_review
from data.quotes import StockQuote, stock_quote
from data.review_store import ReviewStore
from models.investment_review import (
    CASE_NAMES,
    POSITION_TYPES,
    CashFlowAdjustment,
    InvestmentReview,
    ReviewCase,
)
from models.valuation import DcfAssumptions, default_scenarios

MODE_KEY = "esmt_tool"
TICKER_KEY = "esmt_ticker"
HISTORY_KEY = "esmt_review_history"
QUOTES_KEY = "esmt_review_quotes"
MILLION = 1_000_000


def _store():
    path = os.environ.get("ESMT_REVIEW_DB")
    return ReviewStore(path) if path else None


def review_history():
    store = _store()
    if not store:
        return st.session_state.get(HISTORY_KEY, {})
    try:
        return store.recent()
    except (OSError, sqlite3.Error, ValueError) as exc:
        st.error(f"Could not load saved reviews: {exc}")
        return {}


def _save_review(review):
    store = _store()
    if store:
        store.save(review)
        return
    review.validate_for_save()
    history = st.session_state.setdefault(HISTORY_KEY, {})
    history[review.ticker] = [*history.get(review.ticker, [])[-1:], review]


def _open_review(ticker, screen_row):
    st.session_state[MODE_KEY] = "Single Stock Analysis"
    st.session_state[TICKER_KEY] = ticker
    st.session_state["esmt_open_review"] = ticker
    st.session_state["esmt_screen_row"] = screen_row


def render_review_link(tickers, key, screen=None):
    if not tickers:
        return
    selected = st.selectbox("Ticker to review", tickers, key=f"{key}_review_ticker")
    row = screen.loc[screen["Ticker"] == selected].iloc[0].to_dict() if screen is not None else None
    st.button("Open investment review", key=f"{key}_open_review", on_click=_open_review, args=(selected, row))


def _amount_in_millions(value):
    return value / MILLION if value is not None else None


def _amount_in_dollars(value):
    return float(value) * MILLION if value is not None else None


def _adjustment_inputs(adjustments):
    rows = [
        {"Adjustment": item.description, "Change ($M)": item.amount / MILLION, "Source": item.source}
        for item in adjustments
    ]
    edited = st.data_editor(
        pd.DataFrame(rows, columns=["Adjustment", "Change ($M)", "Source"]).astype(
            {"Adjustment": "string", "Change ($M)": "float64", "Source": "string"}
        ),
        num_rows="dynamic", hide_index=True,
        column_config={"Source": st.column_config.LinkColumn("Source URL")},
    )
    return edited


def _read_adjustments(frame):
    return [
        CashFlowAdjustment(
            str(row["Adjustment"]) if pd.notna(row["Adjustment"]) else "",
            float(row["Change ($M)"]) * MILLION if pd.notna(row["Change ($M)"]) else float("nan"),
            str(row["Source"]) if pd.notna(row["Source"]) else "",
        )
        for row in frame.dropna(how="all").to_dict("records")
    ]


def _scenario_inputs(cases):
    rows = [
        {
            "Case": name,
            "FCF change ($M)": cases[name].cash_flow_change / MILLION,
            "Growth %": cases[name].assumptions.growth_rate * 100,
            "Required return %": cases[name].assumptions.discount_rate * 100,
            "Terminal growth %": cases[name].assumptions.terminal_growth_rate * 100,
            "Years": cases[name].assumptions.projection_years,
        }
        for name in CASE_NAMES
    ]
    return st.data_editor(
        pd.DataFrame(rows), hide_index=True, disabled=["Case"],
        column_config={"Years": st.column_config.NumberColumn(min_value=1, max_value=20, step=1, required=True)},
    )


def _read_cases(frame):
    return {
        row["Case"]: ReviewCase(
            float(row["FCF change ($M)"]) * MILLION,
            DcfAssumptions(
                float(row["Required return %"]) / 100, float(row["Growth %"]) / 100,
                float(row["Terminal growth %"]) / 100, int(row["Years"]),
            ),
        )
        for row in frame.to_dict("records")
    }


def _render_valuation(review, quote):
    quote_issue = quote.issue()
    price = quote.price if not quote_issue else None
    scenarios, buy_below, implied = review.evaluate(price)
    base = scenarios[1].valuation.fair_value_per_share
    cards = st.columns(4)
    cards[0].metric("Market price", f"${price:,.2f}" if price is not None else "Unavailable")
    cards[1].metric("Normalized cash flow", f"${review.normalized_fcf / MILLION:,.1f}M")
    cards[2].metric("Base value", f"${base:,.2f}")
    cards[3].metric("Buy below", f"${buy_below:,.2f}")
    st.caption(f"Entry price applies a {review.safety_margin:.0%} margin of safety to the base value.")
    if quote_issue:
        st.caption(quote_issue)
    else:
        st.caption(f"Yahoo Finance market quote dated {quote.date} UTC.")
        st.write(implied.message)
    st.dataframe(
        pd.DataFrame([
            {
                "Case": scenario.name,
                "Starting FCF ($M)": scenario.valuation.starting_fcf / MILLION,
                "Value per share": scenario.valuation.fair_value_per_share,
                "Upside/Downside %": scenario.upside_downside,
            }
            for scenario in scenarios
        ]),
        hide_index=True,
        column_config={
            "Value per share": st.column_config.NumberColumn(format="$%.2f"),
            "Upside/Downside %": st.column_config.NumberColumn(format="percent"),
        },
    )
    for scenario in scenarios:
        for warning in scenario.warnings:
            st.warning(f"{scenario.name} case. {warning}")


def render_investment_review(ticker, info, reported_fcf, fcf_basis, net_debt, shares, assumptions):
    quote = stock_quote(info)
    saved = review_history().get(ticker, [])
    initial = saved[-1] if saved else InvestmentReview(
        ticker, "New idea", reported_fcf, fcf_basis, net_debt, shares, 0.20,
        {name: ReviewCase(0, case) for name, case in default_scenarios(assumptions).items()},
    )
    draft_key = f"review_draft_{ticker}"
    with st.expander("Investment Review", expanded=st.session_state.get("esmt_open_review") == ticker or bool(saved)):
        screen = st.session_state.get("esmt_screen_row")
        if screen and screen["Ticker"] == ticker:
            st.caption(
                f"S&P screen value ${screen['Fair Value']:,.2f} using annual FCF "
                f"through {screen['Annual FCF period']}. The review uses the inputs and scenarios below."
            )
        if ticker in {"DECK", "AMAT"} and st.button("Load worked example", key=f"example_{ticker}"):
            st.session_state[draft_key] = worked_review(ticker, initial)
            st.session_state.pop(f"review_preview_{ticker}", None)
        if saved and st.button("Load saved inputs", key=f"saved_{ticker}"):
            st.session_state[draft_key] = saved[-1]
            st.session_state.pop(f"review_preview_{ticker}", None)
        if st.button("Start from latest available data", key=f"refresh_inputs_{ticker}"):
            st.session_state[draft_key] = replace(
                initial, reported_fcf=reported_fcf, fcf_basis=fcf_basis,
                net_debt=net_debt, shares=shares, adjustments=[],
            )
            st.session_state.pop(f"review_preview_{ticker}", None)
        draft = st.session_state.get(draft_key, initial)
        if saved:
            st.caption(f"Last saved review: {saved[-1].reviewed_at[:10]} UTC")
        if not _store():
            st.caption("Reviews are saved in this session. Use Review Watchlist to download a backup.")
        with st.form(f"investment_review_{ticker}"):
            position = st.selectbox("Position", POSITION_TYPES, index=POSITION_TYPES.index(draft.position))
            inputs = st.columns(3)
            fcf = inputs[0].number_input("Reported or mid-cycle FCF ($M)", value=_amount_in_millions(draft.reported_fcf), step=1.0)
            debt = inputs[1].number_input("Debt less excess cash ($M)", value=_amount_in_millions(draft.net_debt), step=1.0)
            share_count = inputs[2].number_input(
                "Shares outstanding (M)", value=_amount_in_millions(draft.shares), step=1.0, format="%.6f",
            )
            basis = st.text_input("Starting cash flow source and period", value=draft.fcf_basis)
            st.caption("Enter a negative amount to remove a cash-flow benefit. Use cash flows before financing when adding excess cash and subtracting debt.")
            adjustments = _adjustment_inputs(draft.adjustments)
            st.caption("Scenario cash-flow changes are added to the normalized starting cash flow above.")
            cases = _scenario_inputs(draft.cases)
            safety = st.number_input("Margin of safety for entry (%)", min_value=0.0, max_value=99.0, value=draft.safety_margin * 100)
            thesis = st.text_area("Why would you own this business for years?", value=draft.thesis)
            evidence = st.text_area("Evidence, operating metrics, and source links", value=draft.evidence)
            reconsider = st.text_area("What would change your mind?", value=draft.reconsider_if)
            preview = st.form_submit_button("Calculate review")
            save = st.form_submit_button("Save review")
        selected = st.session_state.get(f"review_preview_{ticker}", draft)
        if preview or save:
            try:
                selected = InvestmentReview(
                    ticker=ticker,
                    position=position,
                    reported_fcf=_amount_in_dollars(fcf),
                    fcf_basis=basis,
                    net_debt=_amount_in_dollars(debt),
                    shares=_amount_in_dollars(share_count),
                    safety_margin=safety / 100,
                    cases=_read_cases(cases),
                    adjustments=_read_adjustments(adjustments),
                    thesis=thesis,
                    evidence=evidence,
                    reconsider_if=reconsider,
                    reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    quote_price=quote.price if not quote.issue() else None,
                    quote_date=quote.date if not quote.issue() else "",
                )
                selected.evaluate()
                st.session_state[f"review_preview_{ticker}"] = selected
                if save:
                    _save_review(selected)
                    st.session_state[draft_key] = selected
                    st.session_state.setdefault(QUOTES_KEY, {})[ticker] = quote
                    st.success(f"Saved {ticker} to Review Watchlist.")
            except (TypeError, ValueError, OverflowError, OSError, sqlite3.Error) as exc:
                st.error(str(exc))
                return
        if preview or save or saved or draft_key in st.session_state:
            try:
                _render_valuation(selected, quote)
            except ValueError as exc:
                st.info(str(exc))


def _watchlist_backup(history):
    st.download_button(
        "Download review backup",
        json.dumps([asdict(review) for entries in history.values() for review in entries], indent=2),
        file_name="esmt-reviews.json", mime="application/json",
    )
    if _store():
        return
    backup = st.file_uploader("Restore a session watchlist backup", type="json")
    if backup is not None and st.button("Replace session watchlist with backup"):
        try:
            restored = {}
            for data in json.loads(backup.getvalue()):
                review = InvestmentReview.from_dict(data)
                restored.setdefault(review.ticker, []).append(review)
            st.session_state[HISTORY_KEY] = {
                ticker: sorted(reviews, key=lambda item: item.reviewed_at)[-2:]
                for ticker, reviews in restored.items()
            }
            st.rerun()
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            st.error(f"Could not restore backup: {exc}")


def render_watchlist():
    st.subheader("Review Watchlist")
    history = review_history()
    st.caption(
        "Reviews are saved on this private app instance." if _store() else
        "Reviews are saved in this session. Download a backup to restore them in a later session."
    )
    _watchlist_backup(history)
    if not history:
        st.info("Save a review in Single Stock Analysis to compare a holding and a new idea here.")
        return
    quotes = st.session_state.setdefault(QUOTES_KEY, {})
    if st.button("Check watchlist prices"):
        with st.spinner("Checking Yahoo Finance quotes..."):
            for ticker in history:
                try:
                    quotes[ticker] = stock_quote(load_screen_profile(ticker))
                except Exception:
                    quotes[ticker] = StockQuote(None, None)
    rows = []
    for ticker, revisions in history.items():
        latest = revisions[-1]
        scenarios, buy_below, _ = latest.evaluate()
        bear_value, base_value, _ = [case.valuation.fair_value_per_share for case in scenarios]
        previous_base = revisions[0].evaluate()[0][1].valuation.fair_value_per_share if len(revisions) > 1 else None
        quote = quotes.get(ticker, StockQuote(None, None))
        usable_price = quote.price if not quote.issue() else None
        rows.append({
            "Ticker": ticker, "Position": latest.position, "Price": usable_price,
            "Quote date (UTC)": quote.date, "At entry price": usable_price <= buy_below if usable_price is not None else None,
            "Buy below": buy_below, "Bear value": bear_value, "Base value": base_value,
            "Price change since review %": usable_price / latest.quote_price - 1 if usable_price and latest.quote_price else None,
            "Base value change since previous review %": base_value / previous_base - 1 if previous_base else None,
            "Last reviewed (UTC)": latest.reviewed_at[:10],
        })
    st.dataframe(
        pd.DataFrame(rows).sort_values(["At entry price", "Ticker"], ascending=[False, True]), hide_index=True,
        column_config={
            **{col: st.column_config.NumberColumn(format="$%.2f") for col in ("Price", "Buy below", "Bear value", "Base value")},
            **{col: st.column_config.NumberColumn(format="percent") for col in ("Price change since review %", "Base value change since previous review %")},
        },
    )
    render_review_link(list(history), "watchlist")


def with_reviewed_prices(frame):
    history = review_history()
    if not any(ticker in history for ticker in frame["Ticker"]):
        return frame
    reviewed = {
        ticker: history[ticker][-1].evaluate()[1]
        for ticker in frame["Ticker"] if ticker in history
    }
    return frame.assign(**{"Reviewed buy below": frame["Ticker"].map(reviewed)})
