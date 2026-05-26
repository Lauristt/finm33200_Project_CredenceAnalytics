# FRED / ALFRED

Source id: fred
Official docs: https://fred.stlouisfed.org/docs/api/fred/
Observations docs: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
Authority tier: T2 official/statistical primary for macro verification
License tag: third_party_restricted

Official description summary:
- FRED API v1 lets programs retrieve economic data from FRED and ALFRED by source, release, category, series, tags, and observations.
- FRED API v2 supports bulk retrieval for all series on a release and the entire release history.
- ALFRED vintage/real-time-period fields are important for checking what was known at a historical date.

Use for:
- US and global macroeconomic time-series checks available through FRED.
- CPI, GDP, unemployment, policy rates, Treasury yields, monetary aggregates, and release-level economic data.
- Vintage-aware checks through ALFRED-compatible real-time periods and vintage dates.

Do not use for:
- Company-specific financial statements, issuer identity, or SEC filing facts.
- Claims whose exact official source is outside FRED and where a direct agency API is already available and required.

Important metadata:
- Preserve series_id, observation date, realtime_start, realtime_end, vintage date if supplied, units, frequency, aggregation method, and source/release metadata.
- If a claim is time-sensitive, ask whether current latest value or as-known-on vintage value is needed.
- Treat missing API key, missing vintage date, or revised observations as uncertainty/human-review signals.

Progressive-disclosure guidance:
- First-pass card should only say this source covers macro time series and vintage-aware observations.
- Load this detail for inflation, rates, GDP, unemployment, yields, and other economic series claims.
