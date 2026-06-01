"""Dividend calculation helpers."""

from __future__ import annotations

from typing import Optional

from models.dividend_yield import DividendYieldResolution, resolve_dividend_yield


def estimate_annual_dividend_income(
    investment_amount: float,
    dividend_yield: Optional[float] = None,
    dividend_rate: Optional[float] = None,
    current_price: Optional[float] = None,
) -> Optional[float]:
    """Estimate annual dividend income for a fixed investment amount.

    Yahoo's dividend yield is already annual income divided by price, so it can
    be applied directly to the investment amount. Per-share dividend rates need
    to be converted through the current share price.
    """

    resolved_yield = resolve_dividend_yield(dividend_yield, dividend_rate, current_price)
    if resolved_yield.value is not None:
        return investment_amount * resolved_yield.value

    if dividend_rate is not None and current_price:
        return (investment_amount / current_price) * dividend_rate

    return None
