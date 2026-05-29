from utils.dividends import estimate_annual_dividend_income


def test_estimate_annual_dividend_income_uses_yield_directly():
    assert estimate_annual_dividend_income(10_000, dividend_yield=0.04, current_price=50) == 400


def test_estimate_annual_dividend_income_uses_rate_and_price_fallback():
    assert estimate_annual_dividend_income(10_000, dividend_rate=2.0, current_price=50) == 400


def test_estimate_annual_dividend_income_returns_none_without_inputs():
    assert estimate_annual_dividend_income(10_000) is None
