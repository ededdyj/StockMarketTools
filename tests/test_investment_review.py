from dataclasses import replace

import pytest

from content.review_examples import worked_review
from data.review_store import ReviewStore
from models.investment_review import CashFlowAdjustment, InvestmentReview


def deckers_review():
    return worked_review(
        "DECK", InvestmentReview("DECK", "New idea", 0, "", 0, 1, 0.2, {}),
    )


def test_deckers_review_values_distinct_cash_flow_scenarios():
    review = deckers_review()
    scenarios, entry, implied = review.evaluate(86.71)

    assert review.normalized_fcf == 917_542_000
    assert [item.valuation.starting_fcf for item in scenarios] == [800_000_000, 917_542_000, 1_050_000_000]
    assert [item.valuation.fair_value_per_share for item in scenarios] == pytest.approx([71.53, 100.50, 122.83], abs=0.02)
    assert entry == pytest.approx(80.40, abs=0.02)
    assert implied.valid and implied.implied_growth_rate < review.cases["Base"].assumptions.growth_rate


def test_review_store_retains_two_revisions_per_ticker(tmp_path):
    path = tmp_path / "reviews.sqlite3"
    review = deckers_review()
    store = ReviewStore(path)
    store.save(replace(review, thesis="First thesis"))
    store.save(replace(review, thesis="Updated thesis"))
    store.save(replace(review, thesis="Current thesis"))
    store.save(replace(review, ticker="OTHER", position="Holding"))

    history = ReviewStore(path).recent()
    assert [r.thesis for r in history["DECK"]] == ["Updated thesis", "Current thesis"]
    assert history["DECK"][-1].adjustments == review.adjustments
    assert history["OTHER"][-1].position == "Holding"


def test_unsourced_cash_flow_adjustment_cannot_be_saved(tmp_path):
    store = ReviewStore(tmp_path / "reviews.sqlite3")
    review = replace(deckers_review(), adjustments=[CashFlowAdjustment("One-time benefit", -100_000, "")])
    with pytest.raises(ValueError, match="source URL"):
        store.save(review)
    assert store.recent() == {}
