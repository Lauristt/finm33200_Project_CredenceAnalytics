# BEA API

Source id: bea_api
Official docs: https://apps.bea.gov/api/signup/
Open data page: https://www.bea.gov/open-data
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- BEA's data API provides programmatic access to published BEA economic statistics and metadata.
- BEA datasets include national accounts, GDP by industry, input-output, regional data, and international accounts.
- API access requires a BEA UserID/API key.

Use for:
- Official US GDP, NIPA, personal income, industry, regional, input-output, and international transactions claims.
- Claims where BEA is the primary statistical publisher rather than a FRED mirror.
- Period-specific macro values with BEA table and line metadata.

Do not use for:
- Company filings, SEC XBRL facts, security identifiers, or equity market prices.
- BLS-specific labor or price series when BLS is the direct publisher.

Important metadata:
- Preserve dataset name, table name or line code, line description, frequency, year/period, GeoFips if applicable, unit, DataValue, NoteRef, release metadata, API request parameters, and UserID usage status.
- Treat budget-driven table discontinuations, revisions, annual benchmark updates, and table/line ambiguity as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say BEA covers official US economic accounts and metadata.
- Load this detail for GDP, NIPA, personal income, industry, regional, input-output, or international accounts claims.

