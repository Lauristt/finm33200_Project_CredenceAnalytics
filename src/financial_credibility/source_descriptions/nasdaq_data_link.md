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

