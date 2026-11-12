from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from data import fetcher, market_inputs


@pytest.fixture
def price_app(monkeypatch):
    st.cache_data.clear()
    calls = []
    info = {"symbol": "AAPL", "regularMarketPrice": 150.0, "currentPrice": 148.0}
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


def test_week_includes_latest_session(price_app):
    app, _, calls = price_app
    select_timeframe(app, "1 Week")

    assert calls[-1].get("period") == "5d"
    assert "end" not in calls[-1]
    change = next(item for item in app.metric if item.label.startswith("1 Week change"))
    assert change.value == "+9.00 USD"


def test_current_price_uses_quote_independently_of_chart_window(price_app):
    app, _, _ = price_app
    select_timeframe(app, "1 Week")

    assert "Current Price: $150.00" in [item.value for item in app.header]
    next(
        item for item in app.sidebar.selectbox
        if item.label == "Select Time Frame for Price History"
    ).select("1 Month").run()
    assert not app.exception
    assert "Current Price: $150.00" in [item.value for item in app.header]


@pytest.mark.parametrize("invalid_price", [None, float("nan"), 0.0])
def test_missing_quote_labels_historical_fallback(price_app, invalid_price):
    app, info, _ = price_app
    info.update(regularMarketPrice=invalid_price, currentPrice=None)
    select_timeframe(app, "1 Week")

    assert "Latest available close: $149.00" in [item.value for item in app.header]
    assert not any(item.value.startswith("Current Price:") for item in app.header)
