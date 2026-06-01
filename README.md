# StockMarketTools

StockMarketTools is a Streamlit application for investors who rotate between
multiple investment philosophies. The app centralizes:

- **Single-stock deep dives** with profile data, dividend safety, FCF charts, and
  DCF fair value ranges.
- **ChatGPT research prompt exports** that package the single-stock analysis
  output into a copyable prompt for deeper external research and fair-value
  review.
- **S&P 500 “deal” sweeps** that batch-calc intrinsic value to find discounted
  names.
- **Quality vs. Value screeners** that rank uploaded or preset universes by
  value, quality, growth, stability, and financial health.
- **Knowledge Map** that explains the formulas, assumptions, data sources,
  limitations, and learning links behind each calculation-heavy feature.

All data comes from the `yfinance` API and locally maintained ticker lists in
`data/`.

## Investment Philosophy Toggle

Use the sidebar selector to choose an investment philosophy. Each choice loads
different defaults, metrics, and warnings so the UI reflects the targeted playbook:

| Philosophy | Highlights | Recommended Tools |
| --- | --- | --- |
| **Long-term Value/DCF** | Intrinsic value via discounted cash flow, focus on steady FCF and discount-to-fair-value metrics. | Single Stock Analysis, SP500 Deals |
| **Dividend/Income** | Dividend rate, forward yield, payout ratio, and annual income projections for cash-flow stability. | Single Stock Analysis, Quality vs Value Screener |
| **Growth-at-a-Reasonable-Price** | Percentile-based ROE and revenue growth with DCF discounts for growth names still priced reasonably. | Quality vs Value Screener |
| **Momentum/Trend** | Multi-horizon price changes, beta, and trend-centric charts to follow strength/weakness. | Single Stock Analysis |
| **Index/Passive** | ETF and broad allocation focus with attention to expense ratios and diversified tickers. | Single Stock Analysis |

Each philosophy exposes its default assumptions, warnings, and limitations near
the top of the dashboard so users understand what the selected tools are and are
not optimized to do.

## Key Calculations & Assumptions

- **Knowledge Map Maintenance**
  - The app includes a dedicated Knowledge Map tool for learning and auditability.
  - When adding a feature with financial logic, formulas, scoring, or external
    data assumptions, update `content/knowledge_map.py` with the new concept,
    inputs, calculations, transparency surfaces, limitations, and source links.
  - `tests/test_knowledge_map.py` checks that each knowledge node is complete and
    has at least one source link.

- **Discounted Cash Flow (used in Single Stock and SP500 Deals)**
  - Uses a normalized starting Free Cash Flow resolver. Single-stock mode now
    defaults to the best available current FCF source: SEC Companyfacts TTM for
    U.S. companies when 10-Q/10-K data supports it, then yfinance TTM cash flow,
    then yfinance quarterly TTM, and finally annual yfinance cash flow.
  - FCF is calculated as `FreeCashFlow = OperatingCashFlow - abs(CapitalExpenditures)`.
    The `abs()` treatment is intentional because data providers often report
    capex as a negative cash-flow line even though DCF needs it as a cash outflow.
  - SEC TTM FCF uses `latest annual FCF + current-year YTD FCF - prior-year
    same-period YTD FCF` when quarterly/YTD 10-Q facts are available.
  - Single-stock mode also supports latest fiscal-year FCF, 3-year average FCF,
    a TTM fallback mode, and user-entered normalized FCF.
  - Projects cash flow for *n* years (default `n = 5`) with growth rate `g`.
  - Present value `EV = Σ (FCF_t / (1 + r)^t) + TerminalValue`, where
    `TerminalValue = FCF_n * (1 + g_terminal) / (r - g_terminal)`.
  - Equity value = `EV - NetDebt`, where `NetDebt = TotalDebt - Cash & Equivalents`
    sourced from the latest Yahoo Finance balance sheet (Long Term + Short Term
    debt is used when `Total Debt` is missing).
  - Fair value per share = `Equity Value / Shares Used`; the UI disables
    per-share output if no reliable share count is available.
  - Single-stock mode now shows the full DCF equity bridge: starting FCF,
    projected FCF by year, PV of explicit FCF, terminal value, PV of terminal
    value, enterprise value, cash, debt, net debt, equity value, shares used, and
    fair value per share.
  - Confidence intervals vary discount/growth ± small bands to illustrate
    sensitivity.
  - Single-stock mode adds bull/base/bear scenarios, discount-rate vs terminal
    growth sensitivity, and reverse DCF implied-growth output.
  - In single-stock mode, the sidebar starts from dynamic ticker-specific
    assumptions and still lets the user edit every input. A reset button restores
    the generated defaults for the selected ticker. Inputs are validated so
    discount rate must remain between -50% and 50% and greater than the terminal
    growth rate; invalid combinations block the DCF output with an on-screen
    warning.
  - Dynamic discount-rate defaults use a WACC-style estimate:
    `WACC = equity_weight × cost_of_equity + debt_weight × after_tax_cost_of_debt`.
    Cost of equity uses CAPM:
    `risk_free_rate + beta × equity_risk_premium`. Beta comes from Yahoo Finance
    and is clamped to 0.60-2.00. Debt/equity weights use market cap and latest
    debt when available.
  - Dynamic growth defaults blend usable recent Free Cash Flow growth and
    revenue growth, then clamp the result to 0%-12%. If annual FCF is missing,
    the app can use quarterly operating-cash-flow/capex history before falling
    back to 3%.
  - Dynamic terminal growth is capped conservatively at the minimum of the
    long-term risk-free rate, 3%, and `discount_rate - 1%`.
  - The DCF “Assumptions & Data” expander shows the generated value, source, and
    formula for every dynamic assumption so the defaults remain auditable.

- **Net Debt & Shares Fallbacks**
  - Cash and debt line items prefer yfinance quarterly balance-sheet data when
    available, then fall back to annual balance-sheet data, and finally to zero
    with a warning if Yahoo Finance omits them. The “Assumptions & Data”
    expander shows which fields were used and the balance-sheet “as-of” date.
  - Revenue, net income, and EPS provenance now prefers TTM values derived from
    the latest four yfinance quarterly income-statement periods, then annual
    financials, then Yahoo profile fields.
  - Shares are resolved from filing-derived diluted/common share counts,
    `sharesOutstanding`, `impliedSharesOutstanding`, and
    `marketCap / currentPrice`. Stale filing-derived diluted weighted-average
    shares are not automatically preferred when current Yahoo/implied shares are
    consistent with market cap. The app compares all candidates and warns when
    they materially disagree.
  - Share-count differences above 10% show a warning; differences above 25% or
    candidates that differ by about 2x are marked as valuation data-quality risk.
    Missing/zero values disable per-share DCF output.

- **DCF Data Quality**
  - Single-stock mode centralizes valuation warnings near the DCF output:
    suspicious dividend yield/payout ratio, negative book value, share-count
    mismatches, clamped growth assumptions, terminal-growth/discount-rate risk,
    stale balance sheets, missing cash/debt fallbacks, negative/missing FCF,
    cash-flow/net-income gaps, major share-count changes, and SEC fallback
    issues.
  - “Assumptions & Data” includes source metadata for major valuation inputs:
    price, market cap, shares used, implied shares, cash, debt, net debt,
    operating cash flow, capex, FCF, revenue, beta, risk-free rate, equity risk
    premium, WACC/discount rate, explicit growth, and terminal growth.
  - Valuation input provenance separates market snapshots, official filing data,
    derived estimates, and fallback estimates. Each major input shows value,
    source, formula, period/as-of date, retrieval timestamp, confidence, and
    freshness label.
  - Common ticker-to-CIK values are cached in code for frequently tested U.S.
    tickers so SEC Companyfacts can still be queried when Streamlit Cloud is
    blocked from `company_tickers.json`.
  - Data freshness labels are: Fresh (0-45 days), Recent (46-120 days), Stale
    (121-365 days), Very stale (over 365 days), and Unknown.
  - Single-stock mode shows a compact Data Timing & Freshness summary and warns
    when current market data is mixed with annual financial statement data older
    than 120 days.
  - DCF Fit labels the model suitability as High, Medium, or Low based on FCF
    availability, warning severity, share reliability, fallbacks, and whether the
    company type often requires a specialized model.
  - Companies with large debt relative to market cap, financing operations, or
    financing receivables trigger a warning that net debt may overstate the
    economic debt deduction. The app discloses this risk but does not
    automatically adjust debt.

- **Value Score (Quality vs Value Screener)**
  - `ValueScore = max((FairValue - Price) / FairValue, 0)`.
  - Discount % = `(FairValue - Price) / Price` to show upside in % terms.

- **Quality/Growth/Stability Scores**
  - ROE, revenue growth, and debt-to-equity pulled from `yfinance.info` then
    converted into percentile ranks inside the chosen universe.
  - Stability score inverts the percentile so lower leverage scores higher.
  - Overall score uses weights from the Growth-at-a-Reasonable-Price philosophy
    (`Value` 35%, `Quality` 25%, `Growth` 15%, `Stability` 10%, and
    `Financial Health` 15% by default).
  - Boolean columns signal whether a name meets the philosophy’s ROE and revenue
    growth thresholds.

- **Financial Health / Piotroski-Style Score**
  - Single-stock mode shows a transparent 0-9 scorecard with every signal,
    formula, pass/fail/N/A outcome, point value, source, latest value, and
    comparison value.
  - Quality vs Value Screener adds `Financial Health Raw Score`,
    `Financial Health Available Signals`, `Financial Health Score`, and
    `Financial Health Details`.
  - The nine signals follow the Piotroski F-Score structure:
    positive ROA, positive operating cash flow, improving ROA, operating cash
    flow above net income, decreasing long-term debt ratio, improving current
    ratio, no share dilution, improving gross margin, and improving asset
    turnover.
  - The app first uses `yfinance` statement data, then fills missing financial
    health fields from the SEC EDGAR `companyfacts` API when a U.S. ticker maps
    to a CIK. Missing fields after both sources are marked `N/A` and disclosed.
    The normalized screener value is conservative:
    `FinancialHealthScore = Score / 9` even when fewer than nine signals are
    available.
  - This is a financial-statement quality check, not a bankruptcy model or a
    buy/sell signal. It is less meaningful for ETFs, banks, insurers, REITs, and
    companies with non-standard financial statements.

- **Dividend/Income Metrics**
  - Forward yield, trailing dividend rate, payout ratio, ex-dividend date, and
    estimated annual cash on $10,000 are shown in USD.
  - Dividends are based on trailing twelve months; confirm payout schedules for
    ADRs or special distributions.

- **ChatGPT Research Prompt Export**
  - Single Stock Analysis includes a copyable/downloadable prompt after the DCF
    output.
  - The prompt includes company context, current market metrics, the app's DCF
    fair value estimate, sensitivity range, active assumptions, dynamic default
    derivation, financial health score, share-count diagnostics, full equity
    bridge, source metadata, data-quality warnings, FCF source selection,
    scenarios, sensitivity table, reverse DCF output, and known app limitations.
  - The prompt instructs ChatGPT to research current filings, earnings releases,
    guidance, news, competitive position, industry conditions, capital returns,
    debt maturities, dilution, and other factors that could change valuation.
  - The prompt includes a “Research Checklist for External Verification” covering
    latest SEC filings, earnings releases, investor presentations, guidance,
    segment trends, margin drivers, working capital, capex, debt maturities,
    financing debt, buybacks, dividends, legal/regulatory risks, macro
    sensitivity, competitive threats, analyst expectations, and evidence that
    would change the valuation.
  - This feature does not make an external API call; it packages the app's local
    output so a user can paste it into ChatGPT or another research workflow.

## Data Sources & Caching

- **Market & fundamentals:** `yfinance` (Yahoo Finance). Request timeout is set
  to 60 seconds to cope with slower responses.
- **DCF market inputs:** the app attempts to pull the latest 10-year Treasury
  rate from FRED (`DGS10`) and the latest parseable Damodaran implied equity
  risk premium table. If either source is unavailable, it falls back to a 4.50%
  risk-free rate and 5.00% mature-market equity risk premium and discloses that
  in the assumption table.
- **Financial health fallback:** SEC EDGAR `companyfacts` API. No API key is
  required. The adapter maps common U.S. GAAP XBRL tags for net income, revenue,
  gross profit, operating cash flow, assets, current assets/liabilities,
  long-term debt, and shares outstanding into the app's financial health model.
- **Ticker universes:** CSV files in `data/` (`*_tickers.csv`) for S&P 500, Dow
  30, Nasdaq 100, Dividend Aristocrats, etc. You can add new universes by
  dropping additional CSVs in that folder.
- **Caching:**
  - `st.cache_data(ttl=900)` wraps single-stock bundles to avoid re-downloading
    quotes, history, and cash flows repeatedly.
  - CSV lookups for ticker universes are cached via `st.cache_data`.
  - Expensive loops (e.g., SP500 analysis) still fetch fresh `yfinance` data but
    leverage cached tickers.

## Running the App Locally

1. **Clone the repo and install dependencies**
   ```bash
   git clone <repo-url>
   cd StockMarketTools
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Launch Streamlit**
   ```bash
   streamlit run app.py
   ```
3. **Choose a philosophy and tool** from the sidebar, then enter tickers or load
   ticker lists as needed.

## Running Tests

With the virtual environment active:

```bash
python -m pytest -q
```

No environment variables are currently required. The app uses free Yahoo Finance
data via `yfinance`, free SEC EDGAR companyfacts data for U.S. filing-company
fallbacks, and local CSV files in `data/`.

Optional:

```bash
export SEC_EDGAR_USER_AGENT="Your Name your.email@example.com"
```

SEC EDGAR requests require an identifying user-agent. The app ships with a
project default, but setting `SEC_EDGAR_USER_AGENT` to your own contact string
is more reliable and aligns with SEC fair-access expectations.

## Notes & Limitations

- Free `yfinance` data can lag official filings and may mark risk metrics as
  `None`; the UI will label missing values clearly.
- Yahoo Finance can throttle or omit fields for some tickers. Batch screeners
  report skipped tickers so missing inputs are visible instead of silently
  disappearing.
- SEC EDGAR fallback only covers companies with SEC CIK mappings and usable
  XBRL facts. It will not fully cover ETFs, many ADRs, and some companies with
  non-standard or custom filing tags.
- Balance-sheet gaps from Yahoo Finance are explicitly flagged and fall back to
  zero for modeling purposes; always cross-check before making capital
  decisions.
- Momentum/Trend mode is visualization-only; no stop-loss or trade execution is
  provided.
