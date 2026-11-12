from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.local_script_runner import LocalScriptRunner
from streamlit.runtime.caching import cache_utils

from data import fetcher, market_inputs, quotes


@pytest.fixture
def price_app(monkeypatch):
    st.cache_data.clear()
    calls = []
    info = {
        "symbol": "AAPL", "regularMarketPrice": 150.0, "currentPrice": 148.0,
        "regularMarketTime": pd.Timestamp("2026-11-12 14:55:00Z").timestamp(),
    }
    # The final daily bar can lag the quote, even when today's bar is included.
    history = pd.DataFrame(
        {"Close": [140.0, 142.0, 144.0, 146.0, 149.0]},
        index=pd.bdate_range("2026-11-06", periods=5, name="Date"),
    )

    def fetch(ticker, timeframe):
        calls.append(timeframe)
        selected = history
        if "start" in timeframe:
            selected = selected.loc[selected.index >= timeframe["start"]]
        if "end" in timeframe:
            # Yahoo's end date is exclusive.
            selected = selected.loc[selected.index < timeframe["end"]]
        return {"info": info.copy(), "history": selected}

    monkeypatch.setattr(fetcher, "get_stock_data", fetch)
    monkeypatch.setattr(fetcher.yf, "Ticker", lambda ticker: SimpleNamespace(info=info.copy()))
    monkeypatch.setattr(quotes, "fetch_quote_info", lambda ticker: info.copy())
    monkeypatch.setattr(
        market_inputs, "get_market_inputs",
        lambda: market_inputs.MarketInputs(0.045, 0.05, "Test", "Test", []),
    )
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
    yield app, info, calls
    st.cache_data.clear()


def select_timeframe(app, label):
    app.run()
    assert not app.exception
    next(
        item for item in app.sidebar.selectbox
        if item.label == "Select Time Frame for Price History"
    ).select(label).run()
    assert not app.exception


@pytest.mark.parametrize("timeframe", ["1 Week", "3 Year"])
def test_history_includes_latest_session(price_app, timeframe):
    app, _, calls = price_app
    select_timeframe(app, timeframe)

    if timeframe == "1 Week":
        assert calls[-1].get("period") == "5d"
    assert "end" not in calls[-1]
    change = next(item for item in app.metric if item.label.startswith(f"{timeframe} change"))
    assert change.value == "+9.00 USD"


def test_current_price_uses_quote_independently_of_chart_window(price_app):
    app, _, _ = price_app
    select_timeframe(app, "1 Week")

    assert "Current Price: $150.00" in [item.value for item in app.header]
    assert any("Nov 12, 2026 09:55 AM EST" in item.value for item in app.caption)
    next(
        item for item in app.sidebar.selectbox
        if item.label == "Select Time Frame for Price History"
    ).select("1 Month").run()
    assert not app.exception
    assert "Current Price: $150.00" in [item.value for item in app.header]


def test_timeframes_share_quote_and_refresh_updates_cached_views(price_app):
    app, info, _ = price_app
    select_timeframe(app, "1 Week")

    for label in ("Intraday (1D)", "1 Month", "3 Month", "1 Year"):
        # A different price is available when each history window is first loaded.
        info["regularMarketPrice"] += 1.0
        next(
            item for item in app.sidebar.selectbox
            if item.label == "Select Time Frame for Price History"
        ).select(label).run()
        assert not app.exception
        assert "Current Price: $150.00" in [item.value for item in app.header]

    next(item for item in app.sidebar.button if item.label == "Refresh company data").click().run()
    assert not app.exception
    assert "Current Price: $154.00" in [item.value for item in app.header]

    # The old one-week bundle still contains the original quote; it must be overridden.
    next(
        item for item in app.sidebar.selectbox
        if item.label == "Select Time Frame for Price History"
    ).select("1 Week").run()
    assert not app.exception
    assert "Current Price: $154.00" in [item.value for item in app.header]


@pytest.mark.parametrize("invalid_price", [None, float("nan"), 0.0])
def test_missing_quote_labels_historical_fallback(price_app, invalid_price):
    app, info, _ = price_app
    info.update(regularMarketPrice=invalid_price, currentPrice=None)
    select_timeframe(app, "1 Week")

    assert "Latest available close: $149.00" in [item.value for item in app.header]
    assert not any(item.value.startswith("Current Price:") for item in app.header)


def test_shared_quote_failure_does_not_reuse_timeframe_quote(price_app, monkeypatch):
    app, _, _ = price_app

    def fail(ticker):
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(quotes, "fetch_quote_info", fail)
    select_timeframe(app, "1 Week")

    assert "Latest available close: $149.00" in [item.value for item in app.header]
    assert not any(item.value.startswith("Current Price:") for item in app.header)
    assert any("Current quote unavailable" in item.value for item in app.warning)


def test_quote_expires_after_fifteen_seconds_without_refetching_history(price_app, monkeypatch):
    app, info, calls = price_app
    clock = [1000.0]
    monkeypatch.setattr(cache_utils, "TTLCACHE_TIMER", lambda: clock[0])
    select_timeframe(app, "1 Week")
    initial_history_calls = len(calls)

    info["regularMarketPrice"] = 151.0
    clock[0] += 14
    app.run()
    assert "Current Price: $150.00" in [item.value for item in app.header]

    clock[0] += 2
    app.run()
    assert not app.exception
    assert "Current Price: $151.00" in [item.value for item in app.header]
    assert len(calls) == initial_history_calls


def test_quote_panel_schedules_automatic_refresh(price_app, monkeypatch):
    app, _, _ = price_app
    timers = []
    enqueue = LocalScriptRunner._enqueue_forward_msg

    def capture(self, msg):
        if msg.WhichOneof("type") == "auto_rerun":
            timers.append((msg.auto_rerun.interval, msg.auto_rerun.fragment_id))
        return enqueue(self, msg)

    monkeypatch.setattr(LocalScriptRunner, "_enqueue_forward_msg", capture)
    app.run()

    assert not app.exception
    assert timers
    assert all(interval == 15 and fragment_id for interval, fragment_id in timers)
