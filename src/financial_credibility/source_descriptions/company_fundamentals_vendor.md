# Financial Data Vendor Fundamentals

Source id: company_fundamentals_vendor
Reference docs:
- Alpha Vantage: https://www.alphavantage.co/documentation/
- Finnhub: https://finnhub.io/docs/api/
- Financial Modeling Prep: https://site.financialmodelingprep.com/developer/docs
Authority tier: T3 supplemental
License tag: third_party_restricted

Use for:
- Company profile, basic ratios, market cap, sector/industry, and supplemental financial context when official APIs are insufficient.
- Quick discovery before falling back to official SEC evidence for final verification.

Do not use for:
- Primary evidence for official reported financial statement facts when SEC Company Facts or filings are available.
- Claims requiring exact audit-trace provenance from original filings.

Important metadata:
- Preserve vendor, endpoint, request date, ticker, provider timestamp if present, currency/unit, and any source-file or filing reference provided by the vendor.
- Treat vendor-only support as lower-confidence and usually require official-source cross-check for financial-statement claims.

Progressive-disclosure guidance:
- First-pass card should only say this source group covers supplemental vendor fundamentals.
- Load this detail only after official primary sources are not enough or the claim asks for vendor-style overview metrics.
