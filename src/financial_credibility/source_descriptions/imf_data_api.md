# IMF Data API

Source id: imf_data_api
Official docs: https://data.imf.org/en/Resource-Pages/IMF-API
Authority tier: T1 official primary
License tag: third_party_restricted
Adapter status: implemented

Official description summary:
- IMF data is available through SDMX 2.1 and SDMX 3.0 APIs.
- The API can import IMF datasets into applications and data systems.
- IMF data is useful for cross-country macroeconomic, fiscal, external-sector, reserves, and forecast datasets.

Authentication:
- Public IMF SDMX API access does not use an API key.
- Swagger exploration may require a beta portal account sign-in.
- Restricted/authenticated access uses IMF iData account login through Azure AD B2C / MSAL to obtain a bearer token; this is not an API-key flow.
- Use `IMF_BASE_URL=https://api.imf.org/external/sdmx/3.0` for public SDMX 3.0 access.
- Implemented reader uses SDMX 3.0 data queries shaped as `/data/dataflow/{agency}/{dataflow}/+/{series_key}`.
- The reader supports explicit `agency/dataflow/key` calls and a small WEO mapping for country-level GDP growth, inflation, unemployment, and current-account checks.

API playbook:
- Auth/env: no public API key. Base URL is `IMF_BASE_URL=https://api.imf.org/external/sdmx/3.0`; authenticated iData access is bearer-token based, not key based.
- Current endpoint pattern: `GET {IMF_BASE_URL}/data/dataflow/{agency}/{flow}/+/{series_key}`.
- Current params: `dimensionAtObservation=TIME_PERIOD`, `attributes=dsd`, `measures=all`, `includeHistory=false`, plus `startPeriod/endPeriod` from explicit years or `lastNObservations=5`.
- Explicit-call rule: a claim may contain `IMF:AGENCY/FLOW/KEY` or a full `/data/dataflow/...` path; the adapter will use those values directly.
- Starter mapping: IMF/WEO country claims map to `agency=IMF.RES`, `flow=WEO`, and keys like `{country}.{indicator}.A` where indicators include `NGDP_RPCH`, `PCPIPCH`, `BCA_NGDPD`, and `LUR`.
- Response schema: SDMX JSON with `dataSets`, `series`, `observations`, and structures/dimensions. Parser extracts observation period and value.
- Adapter output: return agency, dataflow, key, period, and parsed values. Distinguish WEO forecasts from historical observations in the human-review note when the claim is about future periods.

Use for:
- WEO, Fiscal Monitor, balance of payments, international reserves, CPI, exchange-rate, and cross-country macro claims where IMF is the chosen authority.
- Country comparisons and global macro context.

Do not use for:
- US company filings, security identifiers, or Treasury fiscal values where a direct US source is better.
- Redistributing IMF-derived content without reviewing IMF terms.

Important metadata:
- Preserve dataflow/dataset, SDMX key, country, indicator, frequency, period, value, unit, scale, vintage/release where available, and IMF endpoint.
- Treat IMF license restrictions, public-vs-authenticated access, forecast vs historical data, WEO release vintage, and country-code ambiguity as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say IMF Data API covers IMF SDMX datasets for global macro and fiscal data.
- Load this detail for IMF, WEO, Fiscal Monitor, BOP, reserves, or cross-country macro claims.
