# SEC Recent Filings

Source id: sec_recent_filings
Official docs: https://www.sec.gov/edgar/sec-api-documentation
Endpoint family: https://data.sec.gov/submissions/CIK##########.json
Authority tier: T1 official primary
License tag: public_official

Official description summary:
- SEC developer resources state that EDGAR provides comprehensive access to filings and that company submissions are available through RESTful JSON APIs on data.sec.gov.
- Recent submissions expose filing history, form types, accession numbers, filing dates, and primary document references.
- It is the default primary source for filing-context and disclosure-document claims.

Use for:
- Official filing history, filing dates, form types, accession numbers, and document links.
- Finding relevant 10-K, 10-Q, 8-K, 20-F, 40-F, 6-K, and related disclosure context.
- Narrative or event claims where the next step is to inspect filing text, exhibits, MD&A, risk factors, buyback tables, or management wording.

Do not use for:
- Macro series values, market prices, or legal-entity LEI resolution.
- Numeric financial-statement checks when Company Facts already exposes the relevant XBRL fact.

Important metadata:
- Preserve CIK, company name, ticker, exchange, form type, filing date, report date, accession number, primary document, and SEC archive URL.
- Treat amended filings, missing document links, or ambiguous form selection as human-review triggers.
- Combine with SEC Company Facts for numeric verification and with web search only as supplemental discovery.

Progressive-disclosure guidance:
- First-pass card should only say this source covers official SEC filing history and disclosure context.
- Load this detail when a claim mentions filings, events, management explanation, buybacks, guidance, or a need for official document links.
