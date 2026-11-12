"""Common freshness checks for stock prices used in review decisions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from models.investment_review import finite_number


QUOTE_REFRESH_SECONDS = 15
QUOTE_FIELDS = (
    "regularMarketPrice", "currentPrice", "regularMarketTime",
    "previousClose", "regularMarketPreviousClose",
    "preMarketPrice", "preMarketTime", "postMarketPrice", "postMarketTime",
)


def fetch_quote_info(ticker: str) -> dict:
    """Read current prices from Yahoo's chart feed without reloading fundamentals."""

    stock = yf.Ticker(ticker)
    history = stock.history(
        period="1d", interval="1m", prepost=True, auto_adjust=False,
        timeout=10, raise_errors=True,
    )
    metadata = stock.history_metadata or {}
    price = metadata.get("regularMarketPrice")
    if not finite_number(price) or price <= 0:
        raise ValueError("Yahoo Finance returned no usable current quote.")
    info = {
        "regularMarketPrice": price,
        "currentPrice": price,
        "regularMarketTime": metadata.get("regularMarketTime"),
    }
    # This request covers one day, so the chart baseline is the prior session's close.
    previous_close = next(
        (metadata.get(field) for field in ("chartPreviousClose", "previousClose")
         if finite_number(metadata.get(field)) and metadata[field] > 0),
        None,
    )
    info.update(previousClose=previous_close, regularMarketPreviousClose=previous_close)
    # Extended-hours bars are separate from the regular-session quote.
    if not history.empty and isinstance(history.index, pd.DatetimeIndex) and "Close" in history:
        closes = history["Close"].dropna().sort_index()
        periods = metadata.get("currentTradingPeriod") or {}
        for session in ("pre", "post"):
            period = periods.get(session) or {}
            start, end = period.get("start"), period.get("end")
            if not finite_number(start) or not finite_number(end):
                continue
            timestamps = closes.index.asi8 / 1_000_000_000
            session_closes = closes[(timestamps >= start) & (timestamps < end)]
            if not session_closes.empty:
                info[f"{session}MarketPrice"] = float(session_closes.iloc[-1])
                info[f"{session}MarketTime"] = session_closes.index[-1].timestamp()
    return info


def daily_price_change(info: dict) -> tuple[float | None, float | None]:
    """Return dollar and percent change from the previous regular-session close."""

    price = next(
        (info.get(field) for field in ("regularMarketPrice", "currentPrice")
         if finite_number(info.get(field)) and info[field] > 0),
        None,
    )
    previous_close = next(
        (info.get(field) for field in ("regularMarketPreviousClose", "previousClose")
         if finite_number(info.get(field)) and info[field] > 0),
        None,
    )
    if price is None or previous_close is None:
        return None, None
    change = price - previous_close
    return change, change / previous_close * 100.0


@dataclass(frozen=True)
class StockQuote:
    price: float | None
    as_of: datetime | None

    @property
    def date(self) -> str:
        return self.as_of.date().isoformat() if self.as_of else ""

    def issue(self, now=None) -> str:
        if not finite_number(self.price) or self.price <= 0:
            return "Missing usable price"
        if not self.as_of:
            return "Missing quote timestamp"
        now = now or datetime.now(timezone.utc)
        if not now - timedelta(days=5) <= self.as_of <= now + timedelta(minutes=5):
            return f"Quote timestamp outside the freshness window ({self.date} UTC)"
        return ""


def stock_quote(info: dict) -> StockQuote:
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    timestamp = info.get("regularMarketTime")
    try:
        as_of = datetime.fromtimestamp(float(timestamp), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        as_of = None
    return StockQuote(price, as_of)
