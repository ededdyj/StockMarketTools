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
        title="ChatGPT Research Prompt Export",
        category="Research Workflow",
        summary=(
            "Packages the single-stock dashboard output into a structured prompt for deeper "
            "external research and independent fair-value review."
        ),
        why_it_matters=(
            "The app can calculate a transparent starting valuation, but a complete investment "
            "review also needs current filings, management commentary, industry context, and "
            "risks that are not fully captured by Yahoo Finance fields."
        ),
        inputs=[
            "Company profile, sector, industry, and business summary from Yahoo Finance",
            "Market snapshot metrics such as price, market cap, valuation multiples, beta, and dividends",
            "DCF fair value estimate, sensitivity range, net debt, shares, and active assumptions",
            "Dynamic default derivation table and warnings",
            "Financial health score and all pass/fail/N/A accounting signals",
        ],
        calculations=[
            "Prompt upside/downside = (app fair value per share - current price) / current price",
            "Prompt preserves the same DCF assumptions and health-score results shown on the page",
            "Research checklist asks ChatGPT to verify the app estimate against filings, earnings, guidance, risks, and industry context",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > ChatGPT Research Prompt Export",
            "Copyable prompt text area",
            "Markdown download button",
            "Prompt includes app limitations and asks ChatGPT to separate facts, estimates, and assumptions",
        ],
        limitations=[
            "The export itself does not browse the web or validate current events.",
            "Generated research quality depends on the model and sources used after the prompt is pasted.",
            "Users still need to verify cited sources and assumptions before making decisions.",
        ],
        sources=[
            KnowledgeSource(
                "SEC investor guide to company filings",
                "https://www.investor.gov/introduction-investing/getting-started/researching-investments/how-read-10-k10-q",
                "Explains how investors can use 10-K and 10-Q filings for company research.",
            ),
            KnowledgeSource(
                "SEC EDGAR company search",
                "https://www.sec.gov/edgar/search/",
                "Primary source for company filings that a research prompt should ask ChatGPT to check.",
            ),
            KnowledgeSource(
                "SEC investor guide to analyst reports",
                "https://www.investor.gov/introduction-investing/getting-started/researching-investments/analyst-reports",
                "Useful reminder that analyst views are estimates and should be compared against primary sources.",
            ),
        ],
    ),
    KnowledgeNode(
        title="Share-Count Resolver",
        category="Valuation Inputs",
        summary="Selects the share count used in per-share valuation after comparing filing-derived, Yahoo, and market-cap-implied candidates.",
        why_it_matters="A stale or inconsistent share count can double or halve fair value per share even when enterprise value is reasonable.",
        inputs=[
            "Yahoo Finance sharesOutstanding and impliedSharesOutstanding",
            "Diluted average shares and common/ordinary shares from statements where available",
            "Market cap and current price to compute implied shares",
        ],
        calculations=[
            "Implied shares = market cap / current price",
            "Selected-vs-implied difference = abs(selected - implied) / implied",
            "Warn above 10%, mark risk above 25%, and strongly warn when plausible candidates differ by 2x",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > Share Count Diagnostics",
            "DCF Data-Quality Warnings",
            "ChatGPT Research Prompt Export",
        ],
        limitations=[
            "Market-cap-implied shares depend on Yahoo market cap and price quality.",
            "Filing share counts can lag buybacks, issuance, and class conversions.",
        ],
        sources=[
            KnowledgeSource(
                "SEC guide to 10-K and 10-Q filings",
                "https://www.investor.gov/introduction-investing/getting-started/researching-investments/how-read-10-k10-q",
                "Primary filings are the best source for share-count changes and dilution context.",
            )
        ],
    ),
    KnowledgeNode(
        title="DCF Equity Bridge",
        category="Valuation",
        summary="Shows the path from starting FCF to enterprise value, equity value, shares used, and fair value per share.",
        why_it_matters="The bridge makes it clear whether valuation changes come from operations, debt/cash, or share count.",
        inputs=[
            "Starting free cash flow",
            "DCF assumptions",
            "Cash, debt, net debt, and shares used",
        ],
        calculations=[
            "Enterprise Value = PV explicit FCF + PV terminal value",
            "Net Debt = total debt - cash and equivalents",
            "Equity Value = Enterprise Value - Net Debt",
            "Fair Value per Share = Equity Value / Shares Used",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > DCF Equity Bridge",
            "Assumptions & Data source metadata table",
            "ChatGPT Research Prompt Export",
        ],
        limitations=[
            "The bridge is only as good as the cash flow, debt, cash, and share data feeding it.",
            "It does not replace a full operating forecast model.",
        ],
        sources=[
            KnowledgeSource(
                "Damodaran DCF stable growth notes",
                "https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/dcfstabl.pdf",
                "Reference for DCF structure and terminal value mechanics.",
            )
        ],
    ),
    KnowledgeNode(
        title="Free Cash Flow Normalization",
        category="Valuation Inputs",
        summary="Calculates starting FCF consistently from operating cash flow and capital expenditures, while supporting average and user-normalized inputs.",
        why_it_matters="Capex sign conventions differ across data providers; inconsistent treatment can overstate or understate FCF.",
        inputs=[
            "Operating cash flow",
            "Capital expenditures",
            "Yahoo Free Cash Flow line item fallback",
            "Optional user-entered normalized FCF",
        ],
        calculations=[
            "Free cash flow = operating cash flow - abs(capital expenditures)",
            "3-year average FCF = average of latest three resolved annual FCF values",
            "TTM mode falls back to latest fiscal year when reliable quarterly data is unavailable",
        ],
        transparency_surfaces=[
            "Sidebar DCF Starting FCF controls",
            "DCF Equity Bridge",
            "Assumptions & Data source metadata",
        ],
        limitations=[
            "TTM FCF needs reliable quarterly data, which yfinance may not provide consistently.",
            "Normalized FCF overrides depend on user judgment.",
        ],
        sources=[
            KnowledgeSource(
                "SEC guide to financial statements",
                "https://www.investor.gov/introduction-investing/getting-started/researching-investments/how-read-10-k10-q",
                "Explains the role of financial statements and filings in company analysis.",
            )
        ],
    ),
    KnowledgeNode(
        title="DCF Data-Quality Warnings",
        category="Data Reliability",
        summary="Centralizes valuation warnings for suspicious market data, stale statements, risky assumptions, and missing inputs.",
        why_it_matters="The app should not silently treat incomplete or inconsistent free data as clean valuation evidence.",
        inputs=[
            "Market metrics, dividends, payout ratio, price/book, and share diagnostics",
            "Balance-sheet date, cash/debt fallbacks, FCF snapshot, and SEC fallback warnings",
            "DCF assumptions and dynamic default warnings",
        ],
        calculations=[
            "Flag dividend yield above 15% and payout ratio above 100%",
            "Flag selected share count vs implied shares above 10% and 25%",
            "Flag discount-rate/terminal-growth spreads below 2%",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > DCF Data-Quality Warnings",
            "Assumptions & Data expander",
            "ChatGPT Research Prompt Export",
        ],
        limitations=[
            "Warnings identify risk; they do not prove the data is wrong.",
            "Some sectors naturally trip generic warnings and need sector-specific review.",
        ],
        sources=[
            KnowledgeSource(
                "yfinance project",
                "https://github.com/ranaroussi/yfinance",
                "Documents the unofficial market-data library used by the app.",
            )
        ],
    ),
    KnowledgeNode(
        title="Scenario DCF",
        category="Valuation",
        summary="Calculates bear, base, and bull valuation cases using editable growth, discount, and terminal assumptions.",
        why_it_matters="A single DCF point estimate hides uncertainty; scenarios reveal the range of plausible outcomes.",
        inputs=[
            "Starting FCF",
            "Scenario growth, discount, and terminal growth assumptions",
            "Net debt, shares used, and current price",
        ],
        calculations=[
            "Each scenario reuses the DCF equity bridge",
            "Upside/downside = scenario fair value per share / current price - 1",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > Bull / Base / Bear Scenario Assumptions",
            "Single Stock Analysis > Bull / Base / Bear DCF Scenarios",
            "ChatGPT Research Prompt Export",
        ],
        limitations=[
            "Default scenarios are generic and should be edited for the company thesis.",
            "Scenarios do not model explicit margin, segment, or capital-allocation paths.",
        ],
        sources=[
            KnowledgeSource(
                "Damodaran valuation data and teaching material",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html",
                "Reference material for valuation assumptions and scenario thinking.",
            )
        ],
    ),
    KnowledgeNode(
        title="DCF Sensitivity Analysis",
        category="Valuation",
        summary="Shows how base-case fair value changes as discount rate and terminal growth move around the selected case.",
        why_it_matters="Terminal value and discount rate often drive most DCF variation, so sensitivity is essential for honest interpretation.",
        inputs=[
            "Base-case starting FCF and growth",
            "Discount-rate step grid",
            "Terminal-growth step grid",
        ],
        calculations=[
            "Recalculate fair value for each discount-rate and terminal-growth pair",
            "Mark cells invalid when terminal growth is greater than or too close to discount rate",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > DCF Sensitivity",
            "ChatGPT Research Prompt Export",
        ],
        limitations=[
            "Two-variable sensitivity still omits margin, reinvestment, and share-count uncertainty.",
            "Large terminal values can dominate the table.",
        ],
        sources=[
            KnowledgeSource(
                "Terminal value overview",
                "https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/dcfstabl.pdf",
                "Explains why terminal assumptions need constraints and sensitivity checks.",
            )
        ],
    ),
    KnowledgeNode(
        title="Reverse DCF",
        category="Valuation",
        summary="Estimates the five-year FCF growth rate implied by the current market price under selected discount and terminal assumptions.",
        why_it_matters="Reverse DCF reframes valuation from 'what is it worth?' to 'what must happen for today's price to make sense?'",
        inputs=[
            "Current price",
            "Shares used",
            "Net debt",
            "Starting FCF",
            "Discount rate, terminal growth, and projection years",
        ],
        calculations=[
            "Target equity value = current price x shares used",
            "Target enterprise value = target equity value + net debt",
            "Solve for explicit FCF growth that makes DCF enterprise value equal target enterprise value",
        ],
        transparency_surfaces=[
            "Single Stock Analysis > Reverse DCF",
            "ChatGPT Research Prompt Export",
        ],
        limitations=[
            "The solver searches a bounded growth range and can fail when price implies extreme assumptions.",
            "Reverse DCF explains market-implied expectations, not whether those expectations are likely.",
        ],
        sources=[
            KnowledgeSource(
                "Damodaran cost of capital and valuation material",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html",
                "Background for interpreting required returns and valuation assumptions.",
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
