from content.research_prompt import StockResearchPromptInputs, build_stock_research_prompt
from models.dcf_assumptions import AssumptionLine, DynamicDcfEstimate
from models.financial_health import FinancialHealthResult, HealthSignal
from models.valuation import DcfAssumptions, ValuationResult
from utils.fundamentals import FundamentalsSnapshot


def _fundamentals():
    return FundamentalsSnapshot(
        cash_and_equivalents=10_000_000,
        total_debt=30_000_000,
        net_debt=20_000_000,
        shares_outstanding=1_000_000,
        balance_sheet_as_of="2025-12-31",
        pulled_at="2026-05-31 10:00:00 UTC",
        cash_source="Cash And Cash Equivalents",
        debt_source="Total Debt",
        shares_source="sharesOutstanding",
    )


def _health_result():
    return FinancialHealthResult(
        score=1,
        max_score=9,
        available_signals=2,
        signals=[
            HealthSignal(
                category="Profitability",
                name="Positive ROA",
                formula="Net Income / Total Assets > 0",
                passed=True,
                points=1,
            ),
            HealthSignal(
                category="Leverage/Liquidity",
                name="Current Ratio Improved",
                formula="Current Assets / Current Liabilities improved",
                passed=False,
                points=0,
            ),
        ],
        warnings=[],
    )


def test_build_stock_research_prompt_includes_app_context_and_instructions():
    assumptions = DcfAssumptions(
        discount_rate=0.10,
        growth_rate=0.04,
        terminal_growth_rate=0.025,
        projection_years=5,
    )
    prompt = build_stock_research_prompt(
        StockResearchPromptInputs(
            ticker="XYZ",
            company_name="Example Corp",
            sector="Technology",
            industry="Software",
            business_summary="Builds example software.",
            current_price=80,
            market_cap=100_000_000,
            enterprise_value=120_000_000,
            trailing_pe=20,
            forward_pe=18,
            price_to_book=5,
            profit_margins=0.22,
            beta=1.1,
            dividend_yield=0.01,
            payout_ratio=0.25,
            fundamentals=_fundamentals(),
            financial_health=_health_result(),
            assumptions=assumptions,
            default_assumptions=assumptions,
            dynamic_estimate=DynamicDcfEstimate(
                assumptions=assumptions,
                lines=[
                    AssumptionLine(
                        "Discount rate",
                        0.10,
                        "WACC estimate",
                        "Equity weight x cost of equity + debt weight x after-tax cost of debt",
                    )
                ],
                warnings=[],
            ),
            valuation=ValuationResult(
                enterprise_value=150_000_000,
                equity_value=130_000_000,
                fair_value_per_share=130,
            ),
            fair_value_range=(110, 150),
        )
    )

    assert "Research XYZ (Example Corp) as an equity investment." in prompt
    assert "App fair value estimate per share: $130.00" in prompt
    assert "App fair value sensitivity range: $110.00 to $150.00" in prompt
    assert "Implied upside/downside to app fair value: 62.5%" in prompt
    assert "Score: 1/9" in prompt
    assert "Profitability: Positive ROA = Pass" in prompt
    assert "Build your own fair value estimate and price target range" in prompt
    assert "Please cite the sources you use" in prompt


def test_build_stock_research_prompt_handles_missing_valuation():
    prompt = build_stock_research_prompt(
        StockResearchPromptInputs(
            ticker="NOPE",
            company_name="No Data Inc",
            sector="N/A",
            industry="N/A",
            business_summary="",
            current_price=None,
            market_cap=None,
            enterprise_value=None,
            trailing_pe=None,
            forward_pe=None,
            price_to_book=None,
            profit_margins=None,
            beta=None,
            dividend_yield=None,
            payout_ratio=None,
            fundamentals=_fundamentals(),
            financial_health=_health_result(),
        )
    )

    assert "App fair value estimate per share: N/A" in prompt
    assert "DCF assumptions unavailable or invalid" in prompt
    assert "Dynamic default derivation unavailable" in prompt
