from utils.dividends import estimate_annual_dividend_income, resolve_dividend_yield


def test_estimate_annual_dividend_income_uses_yield_directly():
    assert estimate_annual_dividend_income(10_000, dividend_yield=0.04, current_price=50) == 400


def test_estimate_annual_dividend_income_uses_rate_and_price_fallback():
    assert estimate_annual_dividend_income(10_000, dividend_rate=2.0, current_price=50) == 400


def test_estimate_annual_dividend_income_returns_none_without_inputs():
    assert estimate_annual_dividend_income(10_000) is None


def test_resolve_dividend_yield_corrects_percent_style_yahoo_value():
    resolved = resolve_dividend_yield(
        dividend_yield=0.47,
        dividend_rate=2.12,
        current_price=450.06,
    )

    assert round(resolved.value, 4) == 0.0047
    assert resolved.source == "dividendRate / currentPrice"
    assert resolved.warning


def test_estimate_annual_dividend_income_uses_corrected_yahoo_yield():
    income = estimate_annual_dividend_income(
        10_000,
        dividend_yield=0.47,
        dividend_rate=2.12,
        current_price=450.06,
    )

    assert round(income, 2) == 47.10
