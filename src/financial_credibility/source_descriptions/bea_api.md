# BEA API

Source id: bea_api
Official docs: https://apps.bea.gov/api/signup/
Open data page: https://www.bea.gov/open-data
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- BEA's data API provides programmatic access to published BEA economic statistics and metadata.
- BEA datasets include national accounts, GDP by industry, input-output, regional data, and international accounts.
- API access requires a BEA UserID/API key.
- Implemented reader uses mapped starter NIPA table requests for GDP, PCE price index, and personal income claims.

API playbook:
- Auth/env: requires `BEA_API_KEY`; BEA calls it a `UserID`.
- Current endpoint: `GET https://apps.bea.gov/api/data`.
- Current params: `UserID`, `method=GetData`, `DataSetName`, `TableName`, `Frequency`, `Year`, and `ResultFormat=JSON`. The adapter filters by `LineNumber` after retrieval when a mapped line is known.
- Starter mappings: `GDP/real GDP -> NIPA/T10101/line 1/Q`, `PCE/core PCE -> NIPA/T20804/lines 1 or 25/M`, `personal income -> NIPA/T20600/line 1/M`.
- Response schema: `BEAAPI.Results.Data[]` with fields such as `TimePeriod`, `LineNumber`, `LineDescription`, `DataValue`, `CL_UNIT`, and notes/release metadata when provided.
- Time alignment: use the inferred year/as-of context to bound `Year`; for multi-year claims prefer explicit years over latest values.
- Adapter output: return table/line/frequency and observation rows. If the table/line cannot be mapped, load BEA metadata first instead of guessing.

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
