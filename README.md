# StockMarketTools

StockMarketTools is a Streamlit application for investors who rotate between
multiple investment philosophies. The app centralizes:

- **Single-stock deep dives** with profile data, dividend safety, FCF charts, and
  DCF fair value ranges.
- **S&P 500 “deal” sweeps** that batch-calc intrinsic value to find discounted
  names.
- **Quality vs. Value screeners** that rank uploaded or preset universes by
  value, quality, growth, stability, and financial health.

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

- **Discounted Cash Flow (used in Single Stock and SP500 Deals)**
  - Uses the most recent Free Cash Flow from `yfinance.cashflow`.
  - Projects cash flow for *n* years (default `n = 5`) with growth rate `g`.
  - Present value `EV = Σ (FCF_t / (1 + r)^t) + TerminalValue`, where
    `TerminalValue = FCF_n * (1 + g_terminal) / (r - g_terminal)`.
  - Equity value = `EV - NetDebt`, where `NetDebt = TotalDebt - Cash & Equivalents`
    sourced from the latest Yahoo Finance balance sheet (Long Term + Short Term
    debt is used when `Total Debt` is missing).
  - Fair value per share = `Equity Value / Shares Outstanding`; the UI disables
    per-share output if Yahoo Finance does not supply a reliable share count.
  - Confidence intervals vary discount/growth ± small bands to illustrate
    sensitivity.
  - In single-stock mode, the sidebar exposes editable assumptions (discount
    rate 10%, growth 3%, terminal growth 2%, projection horizon 5 years) with a
    reset-to-defaults button. Inputs are validated so discount rate must remain
    between -50% and 50% and greater than the terminal growth rate; invalid
    combinations block the DCF output with an on-screen warning.

- **Net Debt & Shares Fallbacks**
  - Cash and debt line items fall back to zero with a warning if Yahoo Finance
    omits them. The “Assumptions & Data” expander shows which fields were used
    and the balance-sheet “as-of” date.
  - Shares default to `sharesOutstanding`, then to `impliedSharesOutstanding`.
    Missing/zero values disable per-share DCF output and surface a warning in the
    UI as well as the log panel.

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

## Data Sources & Caching

- **Market & fundamentals:** `yfinance` (Yahoo Finance). Request timeout is set
  to 60 seconds to cope with slower responses.
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
