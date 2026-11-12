# Valuation improvements from the PLTR review

Recorded November 12, 2026. This backlog captures the changes requested after
reviewing the PLTR research export. Priorities reflect the order to implement,
not a prediction that changing assumptions will raise fair value.

## 1. Consistent active DCF assumptions — completed

The PLTR export showed 12% growth / 12.93% discounting in the headline DCF but
5.39% growth / 10.26% discounting in its Base scenario. Scenario widgets retained
old values across ticker and active-assumption changes.

- Calculate the headline, sensitivity range, Base scenario, sensitivity grid,
  and reverse DCF from one active input snapshot.
- Link the single-stock Base scenario to the active sidebar assumptions.
- Reset Bear/Bull rates when the ticker or any active assumption changes; retain
  deliberate edits during ordinary reruns and provide a reset button.
- Use the same starting FCF, net debt, shares, and horizon across these outputs.
- Show active overrides in input provenance; label generated defaults separately.
- Export the same values and include projection years in each scenario.
- Explain which assumptions each sensitivity surface varies. These surfaces
  intentionally describe different stress tests, rather than identical ranges.
- Verify the PLTR input reproduction, headline/Base/grid reconciliation,
  reverse-DCF round trip, ticker changes, resets, and research export.

Independent saved Investment Reviews retain their own explicitly selected cases.

## 2. Multistage revenue-and-margin DCF — planned

Add an initial growth phase, a gradual transition, and mature economics. Model
revenue, operating margins, taxes, and reinvestment separately. Use guidance and
consensus as sourced reference points, with explicit user assumptions thereafter.
Retain the simple conservative model as a labeled scenario. Do not simply remove
the 12% cap or extrapolate recent growth indefinitely.

Acceptance: users can inspect every forecast year, the growth fade, terminal
transition, and the assumptions responsible for differences from the simple DCF.

## 3. Normalized shareholder cash flow — planned

Show a bridge from reported FCF to normalized shareholder economics, including
tax normalization, reinvestment, and stock compensation. Support either an
economic compensation charge or explicit future dilution, with safeguards against
counting the same future awards twice. Reconcile surplus-cash interest with cash
added in the equity bridge to avoid capitalizing the same asset twice.

Acceptance: each adjustment has a source or explicit assumption, and the app
explains the chosen compensation and cash-flow treatment.

## 4. Prominent, more useful reverse DCF — planned

Show what today's price requires in future revenue, margins, and cash flow over
selectable horizons. Distinguish a solver boundary from an economic conclusion;
the current ±50% search limit is not proof that no growth path supports the price.

Acceptance: display the horizon, fixed assumptions, solved variable, numerical
limits, and the resulting business scale in plain language.

## 5. Share-class and debt classification — planned

Reconcile Class A shares, all-class common shares, diluted shares, and the market
capitalization basis. Explain known class/award differences instead of treating
every mismatch as bad data. Separate financing debt from operating leases and
make the cash-flow/lease treatment consistent with the equity bridge.

Acceptance: a reviewer can reconcile selected shares and debt to the filing and
see how using another valid basis changes per-share value.

## 6. Earnings incorporation and freshness — planned

Track the statement period, filing/publication date, retrieval date, and whether
newer earnings or guidance has been incorporated. An earnings release normally
comes after its statement date; that comparison alone should not imply stale data.

Acceptance: distinguish newer information awaiting incorporation from a release
that discusses the statement period already used.

## 7. Suitability, data quality, and valuation uncertainty — planned

Present these separately. A business may suit DCF and have reliable statements
while its growth duration and valuation remain highly uncertain. Show terminal
value dependence and major assumption sensitivities without implying a precise
statistical confidence level.

Acceptance: no single suitability score is presented as confidence in fair value.

## 8. Business-specific operating evidence — planned

Add relevant indicators and sources. For PLTR, candidates include commercial and
government growth, bookings/annualized contract value, retention, customer
additions, receivables, and collections. Distinguish management explanations from
verified subsequent execution.

Acceptance: each indicator has a definition, reporting period, source, trend,
and an explanation of its relevance to the investment thesis.

## Investor-facing decision summary — planned

The main result should answer:

1. Is this a strong business, and what evidence supports that judgment?
2. What is a reasonable bear/base/bull value, under which operating assumptions?
3. What business performance does today's price require?
4. What entry prices meet selected required returns and margins of safety?
5. Which metrics or thresholds would change the assessment?

Keep business quality and price attractiveness distinct. For a long-term investor,
excellent execution can still produce a poor return from an excessive entry price.
