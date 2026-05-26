# Bank of England Database

Source id: bank_of_england
Official docs: https://www.bankofengland.co.uk/statistics
Database: https://www.bankofengland.co.uk/boeapps/database/
Authority tier: T1 official primary
License tag: public_official
Adapter status: planned

Official description summary:
- The Bank of England publishes UK monetary, financial, banking, interest-rate, and exchange-rate statistics.
- Its statistical database supports export/download workflows for time series.
- It is the direct source for many UK monetary and financial statistics.

Use for:
- UK rates, Bank Rate, sterling exchange rates, monetary aggregates, credit, banking, and Bank of England statistical claims.
- UK macro-financial time-series verification.

Do not use for:
- US SEC filings, US Treasury fiscal data, US labor statistics, or security identifier mapping.

Important metadata:
- Preserve series code, observation date, value, unit, frequency, seasonal adjustment, database URL/export URL, and last-updated date where available.
- Treat series-code ambiguity, historical breaks, and release-calendar differences as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say Bank of England covers official UK macro-financial statistics.
- Load this detail for UK, sterling, Bank Rate, BoE, monetary, banking, or exchange-rate claims.

