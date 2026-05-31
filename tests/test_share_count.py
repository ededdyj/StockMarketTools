import pandas as pd

from models.share_count import resolve_share_count
from models.valuation import ValuationResult
from utils.fundamentals import extract_fundamentals


def test_share_count_resolver_uses_yfinance_when_consistent_with_market_cap():
    info = {
        "sharesOutstanding": 100_000_000,
        "marketCap": 5_000_000_000,
        "currentPrice": 50,
    }

    result = resolve_share_count(info)

    assert result.selected_shares == 100_000_000
    assert result.selected_shares_source == "Yahoo Finance sharesOutstanding"
    assert result.selected_vs_implied_pct_diff == 0


def test_share_count_resolver_uses_implied_when_yfinance_is_materially_wrong():
    info = {
        "sharesOutstanding": 325_000_000,
        "marketCap": 65_000_000_000,
        "currentPrice": 100,
    }

    result = resolve_share_count(info)

    assert result.selected_shares == 650_000_000
    assert result.selected_shares_source == "Computed from market cap / current price"
    assert result.data_quality_risk
    assert any("2x" in warning for warning in result.warnings)


def test_dell_style_share_mismatch_does_not_silently_double_fair_value():
    info = {
        "sharesOutstanding": 325_000_000,
        "marketCap": 65_000_000_000,
        "currentPrice": 100,
    }
    balance_sheet = pd.DataFrame(
        {"2025-01-31": [650_000_000]},
        index=["Ordinary Shares Number"],
    )

    fundamentals = extract_fundamentals(info, balance_sheet)
    equity_value = 187_000_000_000
    valuation = ValuationResult(
        enterprise_value=equity_value,
        equity_value=equity_value,
        fair_value_per_share=equity_value / fundamentals.shares_outstanding,
        shares_used=fundamentals.shares_outstanding,
    )

    assert fundamentals.shares_outstanding == 650_000_000
    assert fundamentals.shares_source == "Filing-derived period-end common/ordinary shares"
    assert 285 <= valuation.fair_value_per_share <= 290
    assert valuation.fair_value_per_share < 575


def test_share_count_resolver_reports_missing_shares():
    result = resolve_share_count({})

    assert result.selected_shares is None
    assert result.data_quality_risk
    assert "per-share valuation disabled" in result.warnings[0]
