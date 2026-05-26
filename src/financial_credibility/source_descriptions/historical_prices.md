# Historical Price Series

Source id: historical_prices
Reference sources: Stooq, Yahoo Finance chart endpoints, and similar free price feeds configured by the project.
Stooq data browser: https://stooq.com/db/h/
Authority tier: T3 supplemental
License tag: third_party_restricted

Use for:
- Daily price, return, drawdown, volatility, relative performance, and price-action claims.
- Supplemental checks when the claim is explicitly about market behavior rather than official filing facts.

Do not use for:
- Primary verification of reported financial statement metrics.
- Official exchange-grade market data, tick-level data, or compliance-critical price evidence without a licensed source.

Important metadata:
- Preserve provider, symbol, exchange/market suffix, observation date, open/high/low/close/adjusted close, volume, currency if available, and adjustment policy.
- Treat discrepancies between vendors, missing corporate-action adjustment information, and unavailable dates as uncertainty signals.

Progressive-disclosure guidance:
- First-pass card should only say this source group covers supplemental historical equity prices.
- Load this detail only when a claim is about price, returns, volatility, drawdown, outperformance, or underperformance.
