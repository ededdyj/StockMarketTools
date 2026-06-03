import pandas as pd

from analysis.results import SkippedTicker
from analysis.single_stock_comparison import (
    ComparisonResult,
    build_single_stock_comparison_prompt,
    compare_single_stocks,
    parse_ticker_input,
    score_comparison_rows,
)
from models.valuation import DcfAssumptions


def _row(
    ticker,
    fair_value=120.0,
    price=100.0,
    health=0.7,
    roe=0.2,
    margin=0.15,
    growth=0.08,
    debt_to_equity=50.0,
    high=0,
    medium=0,
):
    return {
        "Ticker": ticker,
        "Company": f"{ticker} Corp",
        "Current Price": price,
        "App Fair Value": fair_value,
        "Upside/Downside %": None if price is None or fair_value is None else (fair_value - price) / price,
        "Financial Health Normalized Score": health,
        "ROE": roe,
        "Profit Margin": margin,
        "Revenue Growth": growth,
        "Debt-to-Equity": debt_to_equity,
        "High Warning Count": high,
        "Medium Warning Count": medium,
        "Missing Data / Warnings": "",
        "DCF Assumptions Used": "Discount 10.0%, Growth 3.0%, Terminal 2.0%, 5 years",
        "Data Freshness Summary": "Balance sheet 2025-12-31; FCF period 2025-12-31",
    }


def test_parse_ticker_input_handles_separators_dedup_and_uppercase():
    raw = "aapl, MSFT\n googl   AAPL\nnvda"

    assert parse_ticker_input(raw) == ["AAPL", "MSFT", "GOOGL", "NVDA"]


def test_parse_ticker_input_respects_max_tickers():
    raw = "AAPL MSFT GOOGL AMZN META NVDA"

    assert parse_ticker_input(raw, max_tickers=3) == ["AAPL", "MSFT", "GOOGL"]


def test_score_comparison_rows_orders_best_value_first():
    df = score_comparison_rows(
        [
            _row("AAA", fair_value=150, price=100, health=0.8, roe=0.2, margin=0.2, growth=0.1),
            _row("BBB", fair_value=90, price=100, health=0.5, roe=0.1, margin=0.05, growth=0.02),
        ]
    )

    assert df.iloc[0]["Ticker"] == "AAA"
    assert df.iloc[0]["Rank"] == 1


def test_missing_fair_value_does_not_rank_first():
    df = score_comparison_rows(
        [
            _row("MISSING", fair_value=None, price=100, health=1.0, roe=0.9, margin=0.5, growth=0.4),
            _row("VALID", fair_value=125, price=100, health=0.6, roe=0.1, margin=0.1, growth=0.05),
        ]
    )

    assert df.iloc[0]["Ticker"] == "VALID"
    assert df.loc[df["Ticker"] == "MISSING", "Warning Penalty"].iloc[0] >= 0.25


def test_warning_penalties_reduce_score():
    clean = score_comparison_rows([_row("AAA", high=0, medium=0)])
    warned = score_comparison_rows([_row("AAA", high=2, medium=2)])

    assert warned.iloc[0]["Overall Comparison Score"] < clean.iloc[0]["Overall Comparison Score"]


def test_compare_single_stocks_reports_skipped_tickers():
    assumptions = DcfAssumptions.defaults()

    result = compare_single_stocks(
        ["AAA", "BAD"],
        assumptions=assumptions,
        data_loader=lambda ticker: {} if ticker == "BAD" else {"info": {"currentPrice": 10}, "cashflow": pd.DataFrame()},
    )

    assert any(skip.ticker == "BAD" and skip.reason == "no_usable_data" for skip in result.skipped)


def test_build_single_stock_comparison_prompt_contains_validation_context():
    assumptions = DcfAssumptions.defaults()
    df = score_comparison_rows(
        [
            {
                **_row("AAA", fair_value=140, price=100),
                "Financial Health Score": 0.70,
                "Quality Score": 0.80,
                "Growth Score": 0.60,
                "Stability Score": 0.50,
                "Warning Penalty": 0.04,
                "Overall Comparison Score": 0.65,
                "Model Verdict": "Worth deeper review",
                "Key Reason": "40.0% app DCF upside/downside; health 0.70",
                "Missing Data / Warnings": "Medium: stale balance sheet",
            }
        ]
    )
    result = ComparisonResult(
        dataframe=df,
        skipped=[SkippedTicker("BAD", "no_usable_data", "No data returned")],
        assumptions=assumptions,
    )

    prompt = build_single_stock_comparison_prompt(result, ["AAA", "BAD"])

    assert "Best Value Today According to App Data" in prompt
    assert "discount rate 10.00%" in prompt
    assert "#1 AAA" in prompt
    assert "Medium: stale balance sheet" in prompt
    assert "BAD: no_usable_data" in prompt
    assert "Do not treat the app ranking as final" in prompt
    assert "Verify the latest SEC filings" in prompt
