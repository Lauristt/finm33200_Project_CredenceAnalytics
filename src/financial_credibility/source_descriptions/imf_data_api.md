# IMF Data API

Source id: imf_data_api
Official docs: https://data.imf.org/en/Resource-Pages/IMF-API
Authority tier: T1 official primary
License tag: third_party_restricted
Adapter status: planned

Official description summary:
- IMF data is available through SDMX 2.1 and SDMX 3.0 APIs.
- The API can import IMF datasets into applications and data systems.
- IMF data is useful for cross-country macroeconomic, fiscal, external-sector, reserves, and forecast datasets.

Use for:
- WEO, Fiscal Monitor, balance of payments, international reserves, CPI, exchange-rate, and cross-country macro claims where IMF is the chosen authority.
- Country comparisons and global macro context.

Do not use for:
- US company filings, security identifiers, or Treasury fiscal values where a direct US source is better.
- Redistributing IMF-derived content without reviewing IMF terms.

Important metadata:
- Preserve dataflow/dataset, SDMX key, country, indicator, frequency, period, value, unit, scale, vintage/release where available, and IMF endpoint.
- Treat IMF license restrictions, forecast vs historical data, WEO release vintage, and country-code ambiguity as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say IMF Data API covers IMF SDMX datasets for global macro and fiscal data.
- Load this detail for IMF, WEO, Fiscal Monitor, BOP, reserves, or cross-country macro claims.

