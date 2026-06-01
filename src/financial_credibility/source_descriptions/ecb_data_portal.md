# ECB Data Portal API

Source id: ecb_data_portal
Official docs: https://data.ecb.europa.eu/help/api/overview
Data API docs: https://data.ecb.europa.eu/help/api/data
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- The ECB Data Portal exposes data and metadata through SDMX REST services.
- ECB statistical dataflows can be queried by dataflow reference, series key, period, and metadata endpoints.
- It is best for euro-area and ECB-published financial and macro statistics.

API playbook:
- Auth/env: no API key. Base URL is `ECB_BASE_URL=https://data-api.ecb.europa.eu/service`.
- Current endpoint pattern: `GET {ECB_BASE_URL}/data/{flow}/{series_key}`.
- Current params: `lastNObservations=3` and `format=csvdata`.
- Starter mappings: EUR/USD `EXR/D.USD.EUR.SP00.A`; deposit facility rate `FM/B.U2.EUR.4F.KR.DFR.LEV`; main refinancing rate `FM/B.U2.EUR.4F.KR.MRR_FR.LEV`; euro-area HICP annual rate `ICP/M.U2.N.000000.4.ANR`.
- Response schema: CSV/SDMX columns usually include `TIME_PERIOD`, `OBS_VALUE`, plus dimensions and attributes such as frequency, unit, currency, adjustment, and title fields.
- Naming rules: construct SDMX keys from flow dimensions; never guess unknown dimensions without loading dataflow/codelist metadata.
- Adapter output: return flow, key, and parsed observation rows. Mark human review if an ECB key is incomplete or the HICP/rate frequency differs from the claim.

Use for:
- Euro-area rates, exchange rates, HICP, banking, monetary aggregates, credit, payment, and ECB-specific statistical claims.
- SDMX metadata-aware checks where dimensions and codelists matter.

Do not use for:
- US company filings, US labor data, US Treasury fiscal data, or security identifier mapping.

Important metadata:
- Preserve dataflow, agency, version, SDMX key, dimensions, observation date, value, unit, frequency, adjustment, updatedAfter/history parameters, and ECB endpoint.
- Treat incomplete SDMX keys, codelist ambiguity, and updatedAfter/history differences as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say ECB Data Portal covers official euro-area statistics via SDMX.
- Load this detail for ECB, euro-area, eurozone, HICP, euro rates, banking, payment, or SDMX metadata claims.
