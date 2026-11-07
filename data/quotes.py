"""Common freshness checks for stock prices used in review decisions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from models.investment_review import finite_number


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
