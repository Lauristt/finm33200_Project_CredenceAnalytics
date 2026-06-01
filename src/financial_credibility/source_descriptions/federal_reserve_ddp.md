# Federal Reserve DDP / Z.1

Source id: federal_reserve_ddp
Official docs: https://www.federalreserve.gov/datadownload/
Release feed: https://www.federalreserve.gov/feeds/datadownload.html
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The Federal Reserve Board Data Download Program provides downloadable data related to selected Board statistical releases.
- Z.1 Financial Accounts releases include PDF, HTML tables, compressed CSV files, and data dictionaries through DDP.
- Several Board releases also have DDP packages and are often mirrored or complemented by FRED.

API playbook:
- Auth/env: no API key for public DDP downloads.
- Discovery endpoint: start at the DDP release pages and release feed to find release packages, CSV zips, and data dictionaries.
- Query/download shape: select release (for example Z.1), table or series code, frequency, and observation period; download the official CSV/package rather than scraping rendered tables.
- Response/schema to normalize: release name, table, series code, observation period, value, unit, frequency, seasonal adjustment, release date, and revision metadata.
- Naming rules: use Board release codes and DDP data dictionaries; do not infer Z.1 table/series codes from loose prose without a metadata lookup.
- Adapter status: planned. Use FRED as temporary fallback for simple rate/macro series, but mark Board-release-specific claims as needing this DDP adapter.
- Adapter output: should return exact release/table/series rows and package URL, with human review when table or code mapping is uncertain.

Use for:
- Federal Reserve Board release-specific verification where the exact Board release package matters.
- Z.1 Financial Accounts, flow-of-funds, household/corporate balance-sheet, consumer credit, bank balance-sheet, and industrial production claims.
- Replaying the official release file and data dictionary instead of relying only on a downstream aggregator.

Do not use for:
- Company financial statement facts.
- SEC filings, legal-entity LEI records, or security-identifier mapping.
- General macro series when FRED already gives sufficient release metadata and no Board-specific package is required.

Important metadata:
- Preserve release name, table, series code, observation period, frequency, unit, seasonal adjustment flag, CSV package URL, data dictionary, release date, and revision notes.
- Treat release revisions, code changes, preview files, or discontinued series as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say DDP covers selected Federal Reserve Board statistical releases.
- Load this detail for Z.1, flow-of-funds, Board release, or release-file replay claims.
