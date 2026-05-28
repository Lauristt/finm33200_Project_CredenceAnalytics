# GLEIF LEI Records

Source id: gleif_entity
Official docs: https://www.gleif.org/en/lei-data/gleif-api
API docs: https://api.gleif.org/docs
Access and use: https://www.gleif.org/en/lei-data/access-and-use-lei-data
Authority tier: T1 official/open entity data
License tag: cc0

Official description summary:
- GLEIF describes the Global LEI Index as the central, authoritative online source for open, standardized, high-quality legal entity reference data.
- Its API supports search, filters, fuzzy matching, and Level 1/Level 2 entity relationship data where available.
- It should be used as an identity layer before financial or market data retrieval.

API playbook:
- Auth/env: no API key.
- Current adapter endpoint: `GET https://api.gleif.org/api/v1/lei-records`.
- Current params: `filter[entity.names]={entity_or_ticker_text}` and `page[size]=3`.
- Response schema: JSON:API style `data[]`; each row has `id` as LEI and `attributes.entity.legalName.name`, registration status, jurisdiction, addresses, and relationship links where available.
- Naming rules: use for legal-entity names or LEIs, not for market tickers unless the ticker is only a temporary entity hint and the result is reviewed.
- Adapter output: return candidate LEIs and legal names. Multiple plausible matches or non-issued/lapsed records should route to human review before financial retrieval.

Use for:
- Legal entity identification, LEI lookup, fuzzy entity-name matching, issuer/counterparty identity checks, and ownership/relationship links when available.
- Disambiguating similarly named organizations before fetching company or market data.
- Mapping LEIs against other identifiers when GLEIF-provided mapping files are available.

Do not use for:
- Financial statement values, macro series, stock prices, investment recommendations, or market-performance claims.

Important metadata:
- Preserve LEI, legal name, registration status, entity status, jurisdiction, legal address, headquarters address, registration authority, and relationship links.
- Treat low-confidence name matches, lapsed/retired LEIs, or multiple plausible entities as human-review triggers.
- Use this as an identity layer, not as a source of financial metrics.

Progressive-disclosure guidance:
- First-pass card should only say this source covers legal-entity identity and LEI records.
- Load this detail when a claim includes ambiguous company names, issuers, counterparties, legal entities, or LEI-related tasks.
