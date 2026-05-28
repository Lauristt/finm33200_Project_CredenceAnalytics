# Nasdaq Data Link

Source id: nasdaq_data_link
Official docs: https://docs.data.nasdaq.com/
Getting started: https://docs.data.nasdaq.com/docs/getting-started
Authority tier: T3 supplemental platform
License tag: third_party_restricted
Adapter status: planned

Official description summary:
- Nasdaq Data Link provides APIs, SDKs, Excel integrations, and other tools for accessing free and premium datasets.
- It includes free and premium data from many sources, including financial, economic, and alternative datasets.
- Most professional datasets require subscription/licensing, so it should be treated as a platform source rather than an official primary source by default.

API playbook:
- Auth/env: usually requires a Nasdaq Data Link API key and dataset subscription. Use a future `NASDAQ_DATA_LINK_API_KEY` env var if this adapter is implemented.
- Endpoint family: REST dataset calls are organized by database code and dataset code; SDKs wrap the same dataset-code semantics.
- Query shape: identify `{database_code}/{dataset_code}`, then pass date filters, column filters, pagination, and transform options allowed by that dataset.
- Response/schema to normalize: dataset code, vendor/source, column names, dates, values, units, refresh timestamp, subscription/license status, and any premium entitlement messages.
- Naming rules: because this is a platform, the dataset code and vendor provenance must be known before retrieval. Do not treat the platform brand as the data publisher.
- Adapter status: planned. Prefer direct official APIs first; use Nasdaq Data Link only when a licensed dataset is explicitly chosen and documented.
- Adapter output: should return dataset-code-specific rows and license/provenance metadata; entitlement failures should be surfaced as configuration issues.

Use for:
- Supplemental or licensed datasets when direct official sources cannot answer a claim.
- Data enrichment, alternative data, or platform-specific datasets with known licensing.

Do not use for:
- Primary official validation when SEC, BEA, BLS, Treasury, FRED, GLEIF, or another direct authority can answer.
- Unlicensed redistribution or training use.

Important metadata:
- Preserve dataset code, database code, vendor/source, subscription/license status, query parameters, observation date, value, unit, and API response metadata.
- Treat premium licensing, vendor provenance, delayed/real-time distinction, and redistribution limits as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say Nasdaq Data Link is a supplemental data platform with free and premium datasets.
- Load this detail only when the claim names Nasdaq Data Link/Quandl or no direct official source covers the requested evidence.
