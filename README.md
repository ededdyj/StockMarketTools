# StockMarketTools

StockMarketTools is a Streamlit application for investors who rotate between
multiple investment philosophies. The app centralizes:

- **Single-stock deep dives** with profile data, dividend safety, FCF charts, and
  DCF fair value ranges.
- **S&P 500 “deal” sweeps** that batch-calc intrinsic value to find discounted
  names.
- **Quality vs. Value screeners** that rank uploaded or preset universes by
  value, quality, growth, and stability.

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
  - Present value `PV = Σ (FCF_t / (1 + r)^t) + TerminalValue`, where
    `TerminalValue = FCF_n * (1 + g_terminal) / (r - g_terminal)`.
  - Enterprise value per share = `(PV - NetDebt) / SharesOutstanding` (net debt
    assumed zero with free data; adjust externally if needed).
  - Confidence intervals vary discount/growth ± small bands to illustrate
    sensitivity.

- **Value Score (Quality vs Value Screener)**
  - `ValueScore = max((FairValue - Price) / FairValue, 0)`.
  - Discount % = `(FairValue - Price) / Price` to show upside in % terms.

- **Quality/Growth/Stability Scores**
  - ROE, revenue growth, and debt-to-equity pulled from `yfinance.info` then
    converted into percentile ranks inside the chosen universe.
  - Stability score inverts the percentile so lower leverage scores higher.
  - Overall score uses weights from the Growth-at-a-Reasonable-Price philosophy
    (`Value` weight defaults to 40% and scales the remaining weights for Quality,
    Growth, and Stability proportionally).
  - Boolean columns signal whether a name meets the philosophy’s ROE and revenue
    growth thresholds.

- **Dividend/Income Metrics**
  - Forward yield, trailing dividend rate, payout ratio, ex-dividend date, and
    estimated annual cash on $10,000 are shown in USD.
  - Dividends are based on trailing twelve months; confirm payout schedules for
    ADRs or special distributions.

## Data Sources & Caching

- **Market & fundamentals:** `yfinance` (Yahoo Finance). Request timeout is set
  to 60 seconds to cope with slower responses.
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
   pip install -r requirements.txt
   ```
2. **Launch Streamlit**
   ```bash
   streamlit run app.py
   ```
3. **Choose a philosophy and tool** from the sidebar, then enter tickers or load
   ticker lists as needed.

## Notes & Limitations

- Free `yfinance` data can lag official filings and may mark risk metrics as
  `None`; the UI will label missing values clearly.
- Intrinsic value assumes net debt = 0; adjust valuations externally for more
  precise capital-structure modeling.
- Momentum/Trend mode is visualization-only; no stop-loss or trade execution is
  provided.
