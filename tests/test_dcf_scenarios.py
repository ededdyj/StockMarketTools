from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from data import fetcher, market_inputs, quotes


SCRIPT = """
import streamlit as st
from models.valuation import DcfAssumptions
from ui.dcf_scenarios import get_user_scenario_assumptions

ticker = st.selectbox("Ticker", ["AAPL", "PLTR"])
growth = st.number_input("Active growth (%)", value=12.0)
discount = st.number_input("Active discount (%)", value=12.93)
terminal = st.number_input("Active terminal (%)", value=3.0)
years = st.number_input("Active years", value=5, step=1)
cases = get_user_scenario_assumptions(
    DcfAssumptions(discount / 100, growth / 100, terminal / 100, years), ticker,
)
st.session_state["resolved_cases"] = cases
"""


def _input(app, label):
    return next(item for item in app.number_input if item.label == label)


def test_base_is_linked_and_custom_bear_bull_survive_ordinary_reruns():
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert not any(item.label.startswith("Base ") for item in app.number_input)
    _input(app, "Bear Growth (%)").set_value(1.0).run()
    _input(app, "Bull Discount (%)").set_value(9.0).run()
    app.run()

    cases = app.session_state["resolved_cases"]
    assert cases["Base"].growth_rate == 0.12
    assert cases["Base"].discount_rate == pytest.approx(0.1293)
    assert cases["Bear"].growth_rate == 0.01
    assert cases["Bull"].discount_rate == 0.09
    assert not app.exception


@pytest.mark.parametrize("label,value", [
    ("Active growth (%)", 8.0), ("Active discount (%)", 11.0),
    ("Active terminal (%)", 2.5), ("Active years", 8),
])
def test_active_changes_reset_custom_rates_and_reanchor_base(label, value):
    app = AppTest.from_string(SCRIPT).run()
    _input(app, "Bear Growth (%)").set_value(1.0).run()
    _input(app, "Bull Growth (%)").set_value(2.0).run()
    _input(app, label).set_value(value).run()
    assert not app.exception
    cases = app.session_state["resolved_cases"]
    assert cases["Bear"].growth_rate == pytest.approx(cases["Base"].growth_rate - 0.03)
    assert cases["Bull"].growth_rate == pytest.approx(cases["Base"].growth_rate + 0.03)
    assert all(case.projection_years == cases["Base"].projection_years for case in cases.values())


def test_ticker_change_and_explicit_reset_clear_old_scenario_rates():
    app = AppTest.from_string(SCRIPT).run()
    _input(app, "Bear Growth (%)").set_value(1.0).run()
    app.selectbox[0].select("PLTR").run()
    assert _input(app, "Bear Growth (%)").value == pytest.approx(9.0)
    _input(app, "Bear Growth (%)").set_value(2.0).run()
    next(item for item in app.button if item.label == "Reset Bear/Bull to active defaults").click().run()
    assert not app.exception
    assert _input(app, "Bear Growth (%)").value == pytest.approx(9.0)


def test_single_stock_page_and_export_reconcile_after_edits_and_ticker_change(monkeypatch):
    st.cache_data.clear()
    info = {
        "symbol": "PLTR", "currentPrice": 171.64, "regularMarketPrice": 171.64,
        "regularMarketTime": pd.Timestamp("2026-11-12 20:28:00Z").timestamp(),
        "previousClose": 172.4, "marketCap": 412_915_597_312,
        "sharesOutstanding": 2_409_153_214, "beta": 1.61,
    }
    cashflow = pd.DataFrame({
        "2025-12-31": [2_000_000_000, -40_000_000],
        "2024-12-31": [1_000_000_000, -30_000_000],
    }, index=["Operating Cash Flow", "Capital Expenditure"])
    ttm = pd.DataFrame({"2026-09-30": [4_097_197_000, -43_241_000]}, index=cashflow.index)
    bundle = {
        "info": info, "cashflow": cashflow, "ttm_cashflow": ttm,
        "history": pd.DataFrame({"Close": [170.0, 171.64]}, index=pd.bdate_range("2026-11-11", periods=2)),
        "balance_sheet": pd.DataFrame({"2026-09-30": [10_561_531_000, 225_267_000]},
                                          index=["Cash And Cash Equivalents", "Total Debt"]),
    }
    monkeypatch.setattr(fetcher, "get_stock_data", lambda ticker, timeframe: bundle)
    monkeypatch.setattr(fetcher.yf, "Ticker", lambda ticker: SimpleNamespace(info=info))
    monkeypatch.setattr(quotes, "fetch_quote_info", lambda ticker: info)
    monkeypatch.setattr(market_inputs, "get_market_inputs", lambda: market_inputs.MarketInputs(
        0.0488, 0.05, "Test risk free", "Test ERP", [],
    ))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    assert not app.exception

    _input(app, "Bear Growth (%)").set_value(1.0).run()
    _input(app, "Growth Rate (%)").set_value(12.0).run()
    _input(app, "Discount Rate (%)").set_value(11.0).run()
    _input(app, "Projection Years").set_value(8).run()
    assert not app.exception
    headline = next(item.value for item in app.metric if item.label == "Fair Value per Share")
    scenario_table = next(item.value for item in app.dataframe if "Scenario" in item.value.columns)
    base = scenario_table.loc[scenario_table["Scenario"] == "Base (Active DCF)"].iloc[0]
    assert base["Fair Value / Share"] == headline
    assert base["Years"] == 8
    assert _input(app, "Bear Growth (%)").value == pytest.approx(9.0)

    prompt = next(item.value for item in app.text_area if item.label == "Copyable prompt")
    assert f"App fair value estimate per share: {headline}" in prompt
    assert f"Base (Active DCF): fair value {headline}, growth 12.00%, discount 11.00%" in prompt
    assert "years 8" in prompt
    assert "Discount Rate / WACC: 0.11 | Category: User assumption" in prompt

    next(item for item in app.sidebar.text_input if item.label == "Enter Stock Ticker").set_value("PLTR").run()
    assert not app.exception
    assert _input(app, "Projection Years").value == 5
    prompt = next(item.value for item in app.text_area if item.label == "Copyable prompt")
    headline = next(item.value for item in app.metric if item.label == "Fair Value per Share")
    assert f"Base (Active DCF): fair value {headline}" in prompt
    st.cache_data.clear()
