import pandas as pd
import pytest

from data import quotes


def test_live_quote_keeps_regular_and_extended_hours_separate(monkeypatch):
    times = pd.to_datetime([
        "2026-11-12 14:00:00Z", "2026-11-12 20:59:00Z", "2026-11-12 21:05:00Z",
    ])
    history = pd.DataFrame({"Close": [149.0, 150.0, 152.0]}, index=times)

    class FakeTicker:
        history_metadata = {
            "regularMarketPrice": 150.5,
            "chartPreviousClose": 151.0,
            "regularMarketTime": pd.Timestamp("2026-11-12 21:00:00Z").timestamp(),
            "currentTradingPeriod": {
                "pre": {
                    "start": pd.Timestamp("2026-11-12 09:00:00Z").timestamp(),
                    "end": pd.Timestamp("2026-11-12 14:30:00Z").timestamp(),
                },
                "post": {
                    "start": pd.Timestamp("2026-11-12 21:00:00Z").timestamp(),
                    "end": pd.Timestamp("2026-11-13 01:00:00Z").timestamp(),
                },
            },
        }

        @property
        def info(self):
            raise AssertionError("Quote polling must not reload company fundamentals")

        def history(self, **kwargs):
            assert kwargs["prepost"] is True
            assert kwargs["auto_adjust"] is False
            return history

    monkeypatch.setattr(quotes.yf, "Ticker", lambda ticker: FakeTicker())
    info = quotes.fetch_quote_info("AAPL")

    assert info["regularMarketPrice"] == 150.5
    assert info["currentPrice"] == 150.5
    assert info["previousClose"] == 151.0
    assert info["regularMarketPreviousClose"] == 151.0
    assert quotes.daily_price_change(info) == pytest.approx((-0.5, -0.5 / 151.0 * 100))
    assert info["preMarketPrice"] == 149.0
    assert info["postMarketPrice"] == 152.0
    assert info["postMarketTime"] == times[-1].timestamp()


def test_live_quote_rejects_missing_provider_price(monkeypatch):
    class FakeTicker:
        history_metadata = {}

        def history(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(quotes.yf, "Ticker", lambda ticker: FakeTicker())

    with pytest.raises(ValueError, match="no usable current quote"):
        quotes.fetch_quote_info("AAPL")


@pytest.mark.parametrize("price, expected", [(171.26, -1.14), (171.10, -1.30), (172.40, 0.0)])
def test_daily_change_compares_with_prior_close(price, expected):
    change, percent = quotes.daily_price_change({"regularMarketPrice": price, "previousClose": 172.40})

    assert change == pytest.approx(expected)
    assert percent == pytest.approx(expected / 172.40 * 100)


@pytest.mark.parametrize("price, previous_close", [(None, 100.0), (100.0, None), (100.0, 0.0), (100.0, float("nan"))])
def test_daily_change_does_not_invent_missing_inputs(price, previous_close):
    assert quotes.daily_price_change({"regularMarketPrice": price, "previousClose": previous_close}) == (None, None)
