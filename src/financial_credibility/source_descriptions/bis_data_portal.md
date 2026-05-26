# BIS Data Portal API

Source id: bis_data_portal
Official docs: https://stats.bis.org/api-doc/v1/
Data portal help: https://data.bis.org/help/tools
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The BIS SDMX RESTful API offers programmatic access to BIS statistical data and metadata released to the public.
- It supports data retrieval and discovery in formats such as JSON, XML, and CSV.
- BIS data is especially useful for global financial stability, international banking, debt securities, and liquidity statistics.

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

