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
