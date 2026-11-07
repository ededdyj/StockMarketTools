"""Inputs and calculations for a filing-backed investment review."""

from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
from urllib.parse import urlparse

from models.valuation import (
    DcfAssumptions,
    calculate_scenario_valuations,
    reverse_dcf_implied_growth,
)

CASE_NAMES = ("Bear", "Base", "Bull")
POSITION_TYPES = ("Holding", "New idea")


def finite_number(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value)


def margin_of_safety(price, value):
    if finite_number(price) and price > 0 and finite_number(value) and value > 0:
        return (value - price) / value
    return None


@dataclass(frozen=True)
class CashFlowAdjustment:
    description: str
    amount: float
    source: str


@dataclass(frozen=True)
class ReviewCase:
    cash_flow_change: float
    assumptions: DcfAssumptions


@dataclass(frozen=True)
class InvestmentReview:
    ticker: str
    position: str
    reported_fcf: float
    fcf_basis: str
    net_debt: float
    shares: float
    safety_margin: float
    cases: dict[str, ReviewCase]
    adjustments: list[CashFlowAdjustment] = field(default_factory=list)
    thesis: str = ""
    evidence: str = ""
    reconsider_if: str = ""
    reviewed_at: str = ""
    quote_price: float | None = None
    quote_date: str = ""

    @property
    def normalized_fcf(self) -> float:
        return self.reported_fcf + sum(item.amount for item in self.adjustments)

    def validate(self) -> None:
        if not self.ticker or self.position not in POSITION_TYPES:
            raise ValueError("Enter a ticker and choose Holding or New idea.")
        if not self.fcf_basis.strip():
            raise ValueError("Enter the source and period of the starting cash flow.")
        if not finite_number(self.reported_fcf) or not finite_number(self.net_debt):
            raise ValueError("Enter finite cash flow and net debt inputs.")
        if not finite_number(self.shares) or self.shares <= 0:
            raise ValueError("Enter a positive share count.")
        if not finite_number(self.safety_margin) or not 0 <= self.safety_margin < 1:
            raise ValueError("Margin of safety must be at least 0% and below 100%.")
        if self.quote_price is not None and (not finite_number(self.quote_price) or self.quote_price <= 0):
            raise ValueError("The review quote must be a positive price.")
        for item in self.adjustments:
            url = urlparse(item.source)
            if not item.description.strip() or not finite_number(item.amount) or url.scheme not in ("http", "https") or not url.netloc:
                raise ValueError("Each adjustment needs a description, a finite amount, and a source URL.")
        if not finite_number(self.normalized_fcf):
            raise ValueError("Normalized cash flow must be finite.")
        if set(self.cases) != set(CASE_NAMES):
            raise ValueError("Enter one bear, base, and bull case.")
        for name, case in self.cases.items():
            valid, error = case.assumptions.validate()
            if not valid:
                raise ValueError(f"{name} case. {error}")
            if not finite_number(case.cash_flow_change) or self.normalized_fcf + case.cash_flow_change <= 0:
                raise ValueError(f"{name} case needs positive starting cash flow.")

    def validate_for_save(self) -> None:
        self.validate()
        if not self.thesis.strip() or not self.reconsider_if.strip():
            raise ValueError("Before saving, record why you would own it and what would change your mind.")

    def evaluate(self, price=None):
        self.validate()
        scenarios = calculate_scenario_valuations(
            self.normalized_fcf,
            self.net_debt,
            self.shares,
            price,
            {name: self.cases[name].assumptions for name in CASE_NAMES},
            starting_fcf_by_scenario={
                name: self.normalized_fcf + case.cash_flow_change for name, case in self.cases.items()
            },
        )
        base = scenarios[1].valuation.fair_value_per_share
        if not finite_number(base) or base <= 0:
            raise ValueError("Base case needs a positive per-share value to set an entry price.")
        assumptions = self.cases["Base"].assumptions
        implied = reverse_dcf_implied_growth(
            price, self.shares, self.net_debt,
            self.normalized_fcf + self.cases["Base"].cash_flow_change,
            assumptions.discount_rate, assumptions.terminal_growth_rate, assumptions.projection_years,
        )
        return scenarios, base * (1 - self.safety_margin), implied

    @classmethod
    def from_dict(cls, data):
        cases = {
            name: ReviewCase(case["cash_flow_change"], DcfAssumptions(**case["assumptions"]))
            for name, case in data["cases"].items()
        }
        adjustments = [CashFlowAdjustment(**item) for item in data["adjustments"]]
        review = cls(**{**data, "cases": cases, "adjustments": adjustments})
        review.validate_for_save()
        review.evaluate()
        return review
