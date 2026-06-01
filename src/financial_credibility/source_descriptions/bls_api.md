# BLS Public Data API

Source id: bls_api
Official docs: https://www.bls.gov/developers/
API features: https://www.bls.gov/bls/api_features.htm
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- The BLS Public Data API gives public access to published historical time series from BLS programs.
- Version 1 is open without registration; Version 2 supports registration keys and allows more data and features.
- Responses can be retrieved as JSON or spreadsheet formats depending on endpoint/version.
- Implemented reader uses the JSON v2 time-series endpoint with mapped starter series for CPI, core CPI, PPI, payrolls, unemployment, wages, and JOLTS.

API playbook:
- Auth/env: `BLS_API_KEY` is optional for v2 but recommended. Without it, quotas/features are lower.
- Current endpoint: `POST https://api.bls.gov/publicAPI/v2/timeseries/data/`.
- Request body: `{"seriesid":[...], "startyear":"YYYY", "endyear":"YYYY", "registrationkey":"..."}` when a key is configured.
- Starter mappings: `CUSR0000SA0` CPI, `CUSR0000SA0L1E` core CPI, `WPUFD4` PPI final demand, `CES0000000001` nonfarm payrolls, `LNS14000000` unemployment, `JTSJOL` job openings, `CES0500000003` average hourly earnings.
- Response schema: `Results.series[].data[]` rows with `year`, `period`, `periodName`, `value`, and `footnotes`.
- Time alignment: infer `startyear/endyear` from explicit years or article as-of date; do not compare a latest BLS release against an old article unless the as-of window is set.
- Adapter output: return series ID, label, period labels, and values; surface seasonal-adjustment ambiguity for human review.

Use for:
- CPI, PPI, employment, unemployment, wages, job openings, productivity, and other BLS survey claims.
- Labor-market and price-statistics checks where BLS is the primary publisher.
- Historical observations by BLS series ID.

Do not use for:
- Company financial statements, SEC filings, legal-entity identity, or Treasury fiscal data.
- BEA national accounts where BEA is the primary publisher.

Important metadata:
- Preserve BLS series ID, survey, year, period, periodName, value, footnotes, seasonal adjustment flag, registration mode, request version, and release timing.
- Treat missing series IDs, one-day API lag, revised observations, or ambiguous seasonal adjustment as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say BLS covers official labor and price time series.
- Load this detail for CPI, PPI, employment, unemployment, payroll, wages, JOLTS, or productivity claims.
