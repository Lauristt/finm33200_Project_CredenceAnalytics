# Financial Data Vendor Fundamentals

Source id: company_fundamentals_vendor
Reference docs:
- Alpha Vantage: https://www.alphavantage.co/documentation/
- Finnhub: https://finnhub.io/docs/api/
- Financial Modeling Prep: https://site.financialmodelingprep.com/developer/docs
Authority tier: T3 supplemental
License tag: third_party_restricted

API playbook:
- Auth/env: supports `ALPHA_VANTAGE_API_KEY`, `FINNHUB_API_KEY`, and `FMP_API_KEY`; missing keys disable that provider.
- Alpha Vantage overview: `GET https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={key}`. Key fields include `Name`, `MarketCapitalization`, `PERatio`, `EPS`, `RevenueTTM`, and `ProfitMargin`.
- Alpha Vantage earnings: `GET https://www.alphavantage.co/query?function=EARNINGS&symbol={ticker}&apikey={key}`. Key fields include `annualEarnings[]`, `fiscalDateEnding`, `reportedEPS`, and `reportedDate`.
- Finnhub profile: `GET https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={key}`. Key fields include `name`, `marketCapitalization`, and `exchange`.
- Finnhub metrics: `GET https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={key}`. Key fields include valuation, margin, growth, and profitability metrics under `metric`.
- FMP profile/income: `GET https://financialmodelingprep.com/stable/profile?symbol={ticker}&apikey={key}` and `GET https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=2&apikey={key}`.
- Adapter rule: use this group only as T3 supplemental evidence. If a claim is about reported SEC facts, route to SEC Company Facts/filings first and only use vendor fundamentals as context.

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
