# BLS Public Data API

Source id: bls_api
Official docs: https://www.bls.gov/developers/
API features: https://www.bls.gov/bls/api_features.htm
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The BLS Public Data API gives public access to published historical time series from BLS programs.
- Version 1 is open without registration; Version 2 requires registration and allows more data and features.
- Responses can be retrieved as JSON or spreadsheet formats depending on endpoint/version.

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

