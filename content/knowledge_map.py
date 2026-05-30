"""Structured knowledge map content for calculation-heavy app features."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeSource:
    title: str
    url: str
    note: str


@dataclass(frozen=True)
class KnowledgeNode:
    title: str
    category: str
    summary: str
    why_it_matters: str
    inputs: list[str]
    calculations: list[str]
    transparency_surfaces: list[str]
    limitations: list[str]
    sources: list[KnowledgeSource] = field(default_factory=list)


KNOWLEDGE_NODES: list[KnowledgeNode] = [
    KnowledgeNode(
        title="Discounted Cash Flow Valuation",
        category="Valuation",
        summary=(
            "Estimates enterprise value from projected free cash flows plus a terminal value, "
            "then subtracts net debt and divides by shares outstanding."
        ),
        why_it_matters=(
            "DCF makes the investment thesis explicit: cash flow, growth, discount rate, "
            "terminal value, debt, and share count all have to be visible assumptions."
        ),
        inputs=[
            "Free Cash Flow from Yahoo Finance cash flow statements",
            "Net debt from balance sheet cash and debt fields",
            "Shares outstanding from Yahoo Finance profile fields",
            "User-editable discount, growth, terminal growth, and projection-year assumptions",
        ],
        calculations=[
            "FCF_t = latest FCF x (1 + growth_rate)^t",
            "Terminal Value = FCF_n x (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)",
            "Enterprise Value = present value of projected FCF + present value of terminal value",
            "Equity Value = Enterprise Value - Net Debt",
            "Fair Value per Share = Equity Value / Shares Outstanding",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > Intrinsic Value (DCF Model)",
            "Assumptions & Data expander",
            "Fair value confidence interval",
            "S&P 500 Deals and Quality vs Value screener fair-value columns",
        ],
        limitations=[
            "Very sensitive to discount rate and terminal growth.",
            "Less meaningful for companies with negative or highly cyclical free cash flow.",
            "Yahoo Finance can omit cash flow, debt, cash, or share-count fields.",
        ],
        sources=[
            KnowledgeSource(
                "Damodaran valuation data and teaching material",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html",
                "Reference point for DCF, cost of capital, and equity risk premium methodology.",
            ),
            KnowledgeSource(
                "Terminal value overview",
                "https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/dcfstabl.pdf",
                "Explains stable-growth terminal value constraints and valuation closure.",
            ),
        ],
    ),
    KnowledgeNode(
        title="Dynamic DCF Default Derivation",
        category="Valuation Inputs",
        summary=(
            "Generates ticker-specific starting assumptions for single-stock DCF while leaving "
            "all values editable by the user."
        ),
        why_it_matters=(
            "A fixed 10% discount rate and 3% growth rate is simple but not company-specific. "
            "Dynamic defaults make the starting case more consistent with each stock's risk, "
            "capital structure, and growth history."
        ),
        inputs=[
            "10-year Treasury proxy from FRED DGS10, with 4.50% fallback",
            "Damodaran implied equity risk premium table, with 5.00% fallback",
            "Yahoo Finance beta, clamped to 0.60-2.00",
            "Market cap, latest debt, interest expense, tax provision, pretax income",
            "Recent free cash flow and revenue history",
        ],
        calculations=[
            "Cost of Equity = Risk-Free Rate + Beta x Equity Risk Premium",
            "Pretax Cost of Debt = Interest Expense / Total Debt, or Risk-Free Rate + 2.00% fallback spread",
            "After-Tax Cost of Debt = Pretax Cost of Debt x (1 - Tax Rate)",
            "WACC = Equity Weight x Cost of Equity + Debt Weight x After-Tax Cost of Debt",
            "Growth Rate = average of usable recent FCF growth and revenue growth, clamped to 0%-12%",
            "Terminal Growth = min(risk-free rate, 3.00%, discount rate - 1.00%)",
        ],
        transparency_surfaces=[
            "Sidebar DCF controls initialize from generated values for each selected ticker",
            "Reset to dynamic defaults button",
            "Assumptions & Data > Dynamic Default Derivation table",
            "Warnings when market-input or growth fallbacks are used",
        ],
        limitations=[
            "External market inputs can be unavailable; fallbacks are disclosed.",
            "Beta from Yahoo Finance is a noisy historical estimate.",
            "Recent growth can overstate future growth, so values are clamped.",
            "Batch screeners keep shared editable defaults because each universe contains many tickers.",
        ],
        sources=[
            KnowledgeSource(
                "Federal Reserve FRED DGS10",
                "https://fred.stlouisfed.org/series/DGS10",
                "Source for 10-year Treasury constant maturity rate used as the US risk-free proxy.",
            ),
            KnowledgeSource(
                "Damodaran implied equity risk premium data",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histimplX.htm",
                "Market-implied US equity risk premium reference table.",
            ),
            KnowledgeSource(
                "Damodaran cost of capital data",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/wacc.html",
                "Industry-level beta, cost of equity, cost of debt, and WACC reference data.",
            ),
            KnowledgeSource(
                "Damodaran cost of capital paper",
                "https://pages.stern.nyu.edu/adamodar/pdfiles/papers/costofcapital.pdf",
                "Methodological background for risk-free rates, equity risk premiums, and cost of capital.",
            ),
        ],
    ),
    KnowledgeNode(
        title="Financial Health / Piotroski-Style Score",
        category="Quality",
        summary=(
            "Scores nine accounting signals across profitability, leverage/liquidity, and "
            "operating efficiency."
        ),
        why_it_matters=(
            "A stock can look cheap because it is deteriorating. Financial health scoring adds "
            "a second lens for whether fundamentals are improving or weakening."
        ),
        inputs=[
            "Income statement: net income, revenue, gross profit",
            "Cash flow statement: operating cash flow",
            "Balance sheet: total assets, long-term debt, current assets, current liabilities, shares",
            "Yahoo Finance statements first, SEC EDGAR companyfacts fallback for U.S. filing companies",
        ],
        calculations=[
            "Positive ROA",
            "Positive operating cash flow",
            "ROA improved year over year",
            "Operating cash flow greater than net income",
            "Long-term debt ratio decreased",
            "Current ratio improved",
            "No share dilution",
            "Gross margin improved",
            "Asset turnover improved",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > Financial Health Score",
            "How the Financial Health Score is Calculated expander",
            "Quality vs Value Screener financial health columns and details",
            "Source and N/A notes for missing statement fields",
        ],
        limitations=[
            "Less meaningful for ETFs, banks, insurers, REITs, and ADRs.",
            "SEC fallback requires a CIK and usable XBRL tags.",
            "The score is a screening aid, not a bankruptcy model or buy/sell signal.",
        ],
        sources=[
            KnowledgeSource(
                "Piotroski F-Score original paper",
                "https://www.rentables.fr/wp-content/uploads/2011/01/Piotroski_Value-Investing.pdf",
                "Original financial statement signal framework for value stocks.",
            ),
            KnowledgeSource(
                "SEC EDGAR APIs",
                "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
                "Official source for companyfacts XBRL filing data.",
            ),
        ],
    ),
    KnowledgeNode(
        title="Quality vs Value Screener",
        category="Screening",
        summary=(
            "Ranks a ticker universe by value, quality, growth, stability, and financial health."
        ),
        why_it_matters=(
            "The screener turns individual calculations into a repeatable comparison workflow "
            "across watchlists, indices, and uploaded CSV universes."
        ),
        inputs=[
            "Ticker universes from local CSV files or uploaded CSV",
            "DCF fair value and current price",
            "ROE, revenue growth, debt-to-equity from Yahoo Finance info",
            "Financial health score from statement data",
        ],
        calculations=[
            "Value Score = max((Fair Value - Price) / Fair Value, 0)",
            "Quality Score = ROE percentile within the active universe",
            "Growth Score = revenue-growth percentile within the active universe",
            "Stability Score = 1 - debt-to-equity percentile",
            "Overall Score = weighted blend of value, quality, growth, stability, and financial health",
        ],
        transparency_surfaces=[
            "Main screener dataframe",
            "Top 20 leader tables by component score",
            "Skipped tickers expander with failure reasons",
            "Financial Health Details column",
        ],
        limitations=[
            "Percentiles are universe-relative and can distort thin universes.",
            "Batch yfinance calls can be slow or throttled.",
            "Some ticker types lack DCF inputs or financial statement fields.",
        ],
        sources=[
            KnowledgeSource(
                "pandas percentile ranking",
                "https://pandas.pydata.org/docs/reference/api/pandas.Series.rank.html",
                "Ranking behavior used for percentile-based component scores.",
            )
        ],
    ),
    KnowledgeNode(
        title="Dividend Income Estimate",
        category="Income",
        summary=(
            "Estimates annual dividend cash generated by a $10,000 position using yield or "
            "per-share dividend rate."
        ),
        why_it_matters=(
            "Income-focused investors need cash-flow estimates that are easy to audit and not "
            "confused with price return."
        ),
        inputs=[
            "Dividend yield from Yahoo Finance when available",
            "Dividend rate and current price fallback",
            "$10,000 fixed investment amount",
        ],
        calculations=[
            "If dividend yield is available: income = investment amount x dividend yield",
            "Otherwise: income = (investment amount / current price) x dividend rate",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > Dividend & Distribution",
            "Est. Dividend on $10k row",
        ],
        limitations=[
            "Forward yields can lag payout changes.",
            "Special dividends and ADR withholding may not be reflected.",
            "This is an annualized estimate, not a payout calendar.",
        ],
        sources=[
            KnowledgeSource(
                "FINRA dividend yield overview",
                "https://www.finra.org/investors/insights/dividend-yield",
                "Plain-language reference for dividend yield interpretation.",
            )
        ],
    ),
    KnowledgeNode(
        title="Data Sources and Fallbacks",
        category="Data Reliability",
        summary=(
            "Documents where the app gets market, statement, ticker-universe, and log data."
        ),
        why_it_matters=(
            "Financial tools are only as reliable as their inputs. The app exposes missing data "
            "instead of silently pretending every field is complete."
        ),
        inputs=[
            "Yahoo Finance via yfinance for market data, profile data, statements, and history",
            "SEC EDGAR companyfacts fallback for U.S. financial statement fields",
            "FRED DGS10 for risk-free rate",
            "Damodaran data pages for implied equity risk premium references",
            "Local CSV files for ticker universes",
        ],
        calculations=[
            "Cached single-stock data uses Streamlit cache with a 900-second TTL",
            "Ticker CSVs are cached with Streamlit cache_data",
            "Screeners collect skipped-ticker reasons for missing inputs and exceptions",
        ],
        transparency_surfaces=[
            "Warnings for missing Yahoo sections",
            "Skipped tickers expanders",
            "Application Logs expander",
            "Assumptions & Data source notes",
        ],
        limitations=[
            "Free data can be delayed, incomplete, or throttled.",
            "SEC fallback covers filing companies, not all global securities.",
            "External market-input pages may change format; fallbacks are disclosed.",
        ],
        sources=[
            KnowledgeSource(
                "yfinance project",
                "https://github.com/ranaroussi/yfinance",
                "Library used for Yahoo Finance data access.",
            ),
            KnowledgeSource(
                "SEC EDGAR APIs",
                "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
                "Official companyfacts API documentation.",
            ),
            KnowledgeSource(
                "FRED DGS10",
                "https://fred.stlouisfed.org/series/DGS10",
                "Federal Reserve Economic Data 10-year Treasury series.",
            ),
        ],
    ),
]


def get_knowledge_nodes() -> list[KnowledgeNode]:
    return KNOWLEDGE_NODES
