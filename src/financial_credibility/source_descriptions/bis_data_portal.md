# BIS Data Portal API

Source id: bis_data_portal
Official docs: https://stats.bis.org/api-doc/v2/
Data portal help: https://data.bis.org/help/tools
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- The BIS SDMX RESTful API offers programmatic access to BIS statistical data and metadata released to the public.
- It supports data retrieval and discovery in formats such as JSON, XML, and CSV.
- BIS data is especially useful for global financial stability, international banking, debt securities, and liquidity statistics.

Authentication:
- The public BIS Stats API does not require an API key, token, or registration.
- Use `BIS_BASE_URL=https://stats.bis.org/api/v2`.
- v2 data queries use `/data/{context}/{agencyID}/{resourceID}/{version}/{key}`; this project uses `/data/dataflow/BIS/{dataset}/1.0/{series_key}` for mapped series.

API playbook:
- Auth/env: no key. Base URL is `BIS_BASE_URL=https://stats.bis.org/api/v2`.
- Current endpoint pattern: `GET {BIS_BASE_URL}/data/dataflow/BIS/{flow}/1.0/{series_key}`.
- Current params: `lastNObservations=3` and `format=csv`.
- Starter mappings: locational banking `WS_LBS_D_PUB/Q.S.C.A.TO1.A.5J.A.US.A.5J.N`; debt securities `WS_DEBT_SEC2_PUB/Q.US.3P.G.1.C.A.D.TO1.A.U.A.A.A.I`.
- Response schema: CSV/SDMX columns include observation period/value plus flow-specific country, sector, currency, instrument, maturity, and unit dimensions.
- Naming rules: use BIS dataflow metadata to assemble series keys; a wrong dimension order can return empty or misleading data.
- Adapter output: return flow, key, URL, and parsed observations. Treat country/sector/instrument mismatch as human review rather than forcing a verdict.

Use for:
- International banking, cross-border claims, debt securities, global liquidity, and financial stability statistics.
- SDMX metadata checks for BIS-published datasets.

Do not use for:
- Company SEC facts, US labor statistics, legal entity LEI records, or market-price claims.

Important metadata:
- Preserve dataflow, SDMX key, observation period, value, unit, frequency, adjustment, codelists, availability constraints, download format, and API URL.
- Treat SDMX key ambiguity, country/sector dimension mismatch, and release-cycle differences as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say BIS Data Portal covers official global financial statistics via SDMX.
- Load this detail for BIS, international banking, cross-border banking, debt securities, liquidity, or financial stability claims.
