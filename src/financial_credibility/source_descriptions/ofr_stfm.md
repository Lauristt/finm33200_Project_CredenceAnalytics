# OFR Short-term Funding Monitor

Source id: ofr_stfm
Official docs: https://www.financialresearch.gov/short-term-funding-monitor/api/
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The Office of Financial Research STFM API lets remote applications query short-term funding monitor data without manual downloads.
- The API exposes series information, mnemonics, single and multiple series data, and dataset-level queries.
- It does not require tokens or registration.

Use for:
- Repo, short-term funding, secured/unsecured funding, money-market, and systemic-risk monitoring claims.
- OFR STFM series checks and spread calculations.

Do not use for:
- Company fundamentals, SEC filing facts, legal-entity identity, or equity price claims.
- Broad macro claims where FRED/BEA/BLS are the direct source.

Important metadata:
- Preserve mnemonic, dataset, series name, observation date, value, unit, data vintage/update date if provided, spread calculation inputs, and API request path.
- Treat daily update cadence, stale series, and mnemonic ambiguity as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say OFR STFM covers official short-term funding market data.
- Load this detail for repo, funding-market, money-market, or OFR systemic-risk claims.

