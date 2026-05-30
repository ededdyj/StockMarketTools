import pandas as pd

from models.financial_health import calculate_financial_health


def _income_statement():
    return pd.DataFrame(
        {
            "2024-12-31": [120.0, 1_000.0, 450.0],
            "2023-12-31": [80.0, 900.0, 360.0],
        },
        index=["Net Income", "Total Revenue", "Gross Profit"],
    )


def _balance_sheet():
    return pd.DataFrame(
        {
            "2024-12-31": [1_000.0, 200.0, 500.0, 250.0, 100.0],
            "2023-12-31": [1_000.0, 250.0, 400.0, 250.0, 110.0],
        },
        index=[
            "Total Assets",
            "Long Term Debt",
            "Current Assets",
            "Current Liabilities",
            "Ordinary Shares Number",
        ],
    )


def _cashflow():
    return pd.DataFrame(
        {
            "2024-12-31": [150.0],
            "2023-12-31": [90.0],
        },
        index=["Operating Cash Flow"],
    )


def test_calculate_financial_health_scores_all_nine_signals():
    result = calculate_financial_health(_income_statement(), _balance_sheet(), _cashflow())

    assert result.score == 9
    assert result.max_score == 9
    assert result.available_signals == 9
    assert result.score_ratio == 1
    assert all(signal.passed for signal in result.signals)


def test_calculate_financial_health_marks_missing_signals_na():
    result = calculate_financial_health(_income_statement(), pd.DataFrame(), _cashflow())

    assert result.score == 3
    assert result.available_signals == 3
    assert any(signal.passed is None for signal in result.signals)
    assert result.warnings


def test_calculate_financial_health_detects_failures():
    income_statement = _income_statement()
    balance_sheet = _balance_sheet()
    cashflow = _cashflow()
    income_statement.loc["Net Income", "2024-12-31"] = -10.0
    cashflow.loc["Operating Cash Flow", "2024-12-31"] = -5.0
    balance_sheet.loc["Long Term Debt", "2024-12-31"] = 300.0

    result = calculate_financial_health(income_statement, balance_sheet, cashflow)
    by_name = {signal.name: signal for signal in result.signals}

    assert by_name["Positive ROA"].passed is False
    assert by_name["Positive Operating Cash Flow"].passed is False
    assert by_name["Long-Term Debt Ratio Decreased"].passed is False
