# CFTC COT Public Reporting

Source id: cftc_cot
Official docs: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
Public Reporting Environment: https://publicreporting.cftc.gov/
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- The CFTC publishes Commitments of Traders reports to help the public understand futures and options market dynamics.
- COT reports provide a breakdown of each Tuesday's open interest for markets meeting CFTC reporting thresholds.
- The Public Reporting Environment provides API-style access for customizing, searching, filtering, and downloading COT data.

API playbook:
- Auth/env: no key required for public COT rows. Optional `CFTC_APP_TOKEN` can be sent as `$$app_token`. Base URL is `CFTC_BASE_URL=https://publicreporting.cftc.gov/resource`.
- Current dataset: `6dca-aqww` for legacy futures-only COT public rows.
- Current endpoint: `GET {CFTC_BASE_URL}/6dca-aqww.json`.
- Current params: `$limit=5`, `$order=report_date_as_yyyy_mm_dd DESC`, optional `$where` clauses for `market_and_exchange_names` and `report_date_as_yyyy_mm_dd <= YYYY-MM-DD`.
- Response schema: rows include `report_date_as_yyyy_mm_dd`, `market_and_exchange_names`, `open_interest_all`, `noncomm_positions_long_all`, `noncomm_positions_short_all`, and category-specific positioning fields.
- Naming rules: map contract language such as WTI, gold, natural gas, S&P, Nasdaq, or Treasury to CFTC market-name fragments, then keep the exact returned market name.
- Adapter output: return report-date-aligned positioning rows and open interest. Do not use COT for cash spot-price claims.

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
