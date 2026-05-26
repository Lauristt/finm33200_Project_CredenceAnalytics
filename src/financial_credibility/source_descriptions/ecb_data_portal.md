# ECB Data Portal API

Source id: ecb_data_portal
Official docs: https://data.ecb.europa.eu/help/api/overview
Data API docs: https://data.ecb.europa.eu/help/api/data
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The ECB Data Portal exposes data and metadata through SDMX REST services.
- ECB statistical dataflows can be queried by dataflow reference, series key, period, and metadata endpoints.
- It is best for euro-area and ECB-published financial and macro statistics.

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

