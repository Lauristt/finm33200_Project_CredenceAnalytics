# OpenFIGI API

Source id: openfigi
Official docs: https://www.openfigi.com/api/documentation
Overview: https://www.openfigi.com/api/overview
Authority tier: T2 identifier infrastructure
License tag: unknown
Adapter status: implemented

Official description summary:
- OpenFIGI maps third-party identifiers to FIGIs and related Open Symbology metadata.
- The API is free and open to the public, with lower rate limits for unauthenticated traffic and higher limits with an API key.
- It is an instrument-identifier mapping layer, not a financial statement or macro data source.

API playbook:
- Auth/env: `OPENFIGI_API_KEY` is optional but recommended for higher rate limits. Send it as header `X-OPENFIGI-APIKEY`.
- Current endpoint: `POST https://api.openfigi.com/v3/mapping`.
- Request body: a JSON array of mapping jobs such as `{"idType":"TICKER","idValue":"AAPL","exchCode":"US"}` or `{"idType":"ID_ISIN","idValue":"..."}`.
- Current adapter rule: infer `idType/idValue` from the claim; ticker lookups add `exchCode=US` by default.
- Response schema: list of blocks; each block may contain `data[]` rows with `figi`, `compositeFIGI`, `shareClassFIGI`, `ticker`, `name`, `exchCode`, `marketSector`, `securityType`, and related metadata.
- Naming rules: always constrain by exchange/MIC/country when the identifier is not unique. Treat FIGI mapping as identity evidence, not value evidence.
- Adapter output: return top mapping candidates and raw rows; multiple plausible rows require human review before downstream price/fundamental retrieval.

Use for:
- Mapping tickers, ISINs, CUSIPs, SEDOLs, Bloomberg IDs, and other identifiers to FIGI.
- Security-level entity resolution when ticker ambiguity or cross-market identity matters.

Do not use for:
- Company financial statement values.
- Legal entity LEI records, macro observations, or investment recommendations.

Important metadata:
- Preserve idType, idValue, exchCode, micCode, currency, market sector, security type, FIGI, composite FIGI, share class FIGI, ticker, name, and mapping confidence/ambiguity.
- Treat multiple matches, stale identifiers, missing exchange/MIC, and security-type ambiguity as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say OpenFIGI maps market/security identifiers to FIGI.
- Load this detail for ticker ambiguity, ISIN/CUSIP/SEDOL mapping, FIGI, or instrument-level identity claims.
