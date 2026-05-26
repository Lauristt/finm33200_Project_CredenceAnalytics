# CFTC COT Public Reporting

Source id: cftc_cot
Official docs: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
Public Reporting Environment: https://publicreporting.cftc.gov/
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The CFTC publishes Commitments of Traders reports to help the public understand futures and options market dynamics.
- COT reports provide a breakdown of each Tuesday's open interest for markets meeting CFTC reporting thresholds.
- The Public Reporting Environment provides API-style access for customizing, searching, filtering, and downloading COT data.

Use for:
- Futures and options-on-futures positioning, open interest, trader category, and weekly COT trend claims.
- Claims about CFTC-published derivatives market structure data.

Do not use for:
- Single-company financial statement facts.
- Cash equity prices, SEC filings, BEA/BLS macro statistics, or legal-entity LEI lookup.

Important metadata:
- Preserve report type, market name, contract, report date, publication date, trader category, long/short/spreading values, open interest, units, and CFTC dataset/API query.
- Treat report delays, revised historical files, contract-name ambiguity, and weekly vs daily expectation mismatch as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say CFTC COT covers official futures/options positioning data.
- Load this detail for COT, futures positioning, open interest, swaps, or derivatives market-structure claims.

