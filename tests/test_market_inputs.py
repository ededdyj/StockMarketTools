import requests

from data import market_inputs


class _Response:
    def __init__(self, text="", status_error=None):
        self.text = text
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error


def test_fetch_latest_fred_rate_parses_latest_observation(monkeypatch):
    monkeypatch.setattr(
        market_inputs.requests,
        "get",
        lambda *args, **kwargs: _Response("observation_date,DGS10\n2026-01-01,.\n2026-01-02,4.25\n"),
    )

    rate, source = market_inputs._fetch_latest_fred_rate()

    assert rate == 0.0425
    assert "2026-01-02" in source


def test_get_market_inputs_uses_fallbacks_when_sources_fail(monkeypatch):
    market_inputs.get_market_inputs.cache_clear()

    def raise_error(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(market_inputs.requests, "get", raise_error)

    inputs = market_inputs.get_market_inputs()

    assert inputs.risk_free_rate == 0.045
    assert inputs.equity_risk_premium == 0.05
    assert len(inputs.warnings) == 2

    market_inputs.get_market_inputs.cache_clear()


def test_fetch_latest_damodaran_erp_parses_latest_implied_premium(monkeypatch):
    html = """
    <tr><td>2024</td><td>4.00%</td><td>1.20%</td><td>3.80%</td><td>4.50%</td><td>1.18</td></tr>
    <tr><td>2025</td><td>4.10%</td><td>1.10%</td><td>4.00%</td><td>4.75%</td><td>1.19</td></tr>
    """
    monkeypatch.setattr(market_inputs.requests, "get", lambda *args, **kwargs: _Response(html))

    erp, source = market_inputs._fetch_latest_damodaran_erp()

    assert erp == 0.0475
    assert "2025" in source
