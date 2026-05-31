"""Dividend calculation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DividendYieldResolution:
    value: Optional[float]
    source: str
    warning: Optional[str] = None
    raw_yield: Optional[float] = None


def resolve_dividend_yield(
    dividend_yield: Optional[float] = None,
    dividend_rate: Optional[float] = None,
    current_price: Optional[float] = None,
    trailing_annual_dividend_yield: Optional[float] = None,
) -> DividendYieldResolution:
    """Return dividend yield as a decimal after checking Yahoo unit ambiguity.

    yfinance can expose `dividendYield` as a decimal for some tickers and as a
    percent-style number for others. AMAT, for example, can return 0.47 when
    the economic yield is about 0.47%, not 47%. When dividend rate and price are
    available, use them as the sanity-check source for suspicious raw yields.
    """

    derived_yield = None
    if dividend_rate is not None and current_price:
        try:
            if current_price > 0:
                derived_yield = float(dividend_rate) / float(current_price)
        except (TypeError, ValueError):
            derived_yield = None

    if dividend_yield is not None:
        try:
            raw_yield = float(dividend_yield)
        except (TypeError, ValueError):
            raw_yield = None
        if raw_yield is not None:
            if derived_yield is not None and raw_yield > 0.15 and derived_yield <= 0.15:
                return DividendYieldResolution(
                    value=derived_yield,
                    source="dividendRate / currentPrice",
                    warning=(
                        f"Yahoo dividendYield looked unit-scaled ({raw_yield:.2%}); "
                        "using dividend rate divided by current price."
                    ),
                    raw_yield=raw_yield,
                )
            if raw_yield > 1:
                return DividendYieldResolution(
                    value=raw_yield / 100.0,
                    source="Yahoo dividendYield divided by 100",
                    warning="Yahoo dividendYield appeared to be a percent value; divided by 100.",
                    raw_yield=raw_yield,
                )
            return DividendYieldResolution(raw_yield, "Yahoo dividendYield", raw_yield=raw_yield)

    if trailing_annual_dividend_yield is not None:
        try:
            trailing = float(trailing_annual_dividend_yield)
            if trailing > 1:
                trailing /= 100.0
            return DividendYieldResolution(trailing, "Yahoo trailingAnnualDividendYield", raw_yield=dividend_yield)
        except (TypeError, ValueError):
            pass

    if derived_yield is not None:
        return DividendYieldResolution(derived_yield, "dividendRate / currentPrice", raw_yield=dividend_yield)

    return DividendYieldResolution(None, "Unavailable", raw_yield=dividend_yield)


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
