# SEC Company Facts

Source id: sec_company_facts
Official docs: https://www.sec.gov/edgar/sec-api-documentation
Endpoint family: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
Authority tier: T1 official primary
License tag: public_official

Official description summary:
- SEC developer resources state that company submissions and extracted XBRL data are available through RESTful JSON APIs on data.sec.gov.
- Company Facts is the SEC endpoint family for normalized XBRL facts by CIK.
- It is the default primary evidence source for US public-company financial-statement metric claims.

API playbook:
- Auth/env: no API key. Set `SEC_USER_AGENT` to a descriptive contact string and use it on every SEC request.
- Identity step: resolve ticker to CIK with `GET https://www.sec.gov/files/company_tickers.json`; match the uppercase `ticker` and keep `cik_str`.
- Data endpoint: `GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json`.
- Request parameters: none beyond the CIK path. Apply `as_of_date` inside the adapter by ignoring facts whose `filed` date is after the article/time context.
- Response schema: `facts -> {taxonomy} -> {concept} -> units -> {unit}[]`; fact rows expose `val`, `start`, `end`, `filed`, `form`, `frame`, `accn`, and sometimes dimensional metadata.
- Naming rules: map claim language to `SEC_CONCEPTS` first, then allow concept-name fuzzy matching only for clearly related financial-statement terms. Do not use EPS/revenue facts for product-market, supply-chain, price, or quote claims.
- Adapter output: return the matched concept/unit/period rows plus CIK and source URL; mark human review when unit, fiscal period, restatement/amendment, or concept mapping is ambiguous.

Use for:
- US public-company reported financial statement facts extracted from XBRL.
- Numeric checks for revenue, net income, EPS, assets, debt, cash flow, shares, and other taxonomy-backed facts.
- Comparisons across periods when period, unit, accession number, and filing date can be preserved.

Do not use for:
- Management explanation claims that require MD&A wording or narrative attribution.
- Earnings-call transcript, sell-side estimate, news, or market-price claims.
- Custom non-standard company metrics unless the concept mapping is explicitly confirmed.

Important metadata:
- Preserve CIK, taxonomy, concept/tag, unit, value, start/end/instant period, form, filing date, frame, accession number, and source URL.
- Treat amended/restated filings or duplicate values for the same period as human-review triggers unless the parser can choose the correct accession deterministically.
- SEC access should use a descriptive User-Agent and respect fair-access limits.

Progressive-disclosure guidance:
- First-pass card should only say this source covers official SEC XBRL numeric company facts.
- Load this detail only for company financial statement metric claims.
- Prefer this source over vendor fundamentals when the claim is about reported historical financials.
