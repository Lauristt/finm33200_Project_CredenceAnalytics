# Bank of England Database

Source id: bank_of_england
Official docs: https://www.bankofengland.co.uk/statistics
Database: https://www.bankofengland.co.uk/boeapps/database/
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- The Bank of England publishes UK monetary, financial, banking, interest-rate, and exchange-rate statistics.
- Its statistical database supports export/download workflows for time series.
- It is the direct source for many UK monetary and financial statistics.

Authentication:
- The statistical database download endpoint does not require an API key, token, or registration.
- Use `BOE_IADB_BASE_URL=https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp`.
- CSV downloads use URL parameters such as `csv.x=yes`, `Datefrom`, `Dateto`, `SeriesCodes`, `UsingCodes=Y`, `CSVF=TN`, `VPD`, and `VFD`.
- CSV/HTML/XML requests support up to 300 series codes; Excel supports up to 250.

API playbook:
- Auth/env: no key. Base URL is `BOE_IADB_BASE_URL=https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp`.
- Current endpoint: `GET {BOE_IADB_BASE_URL}` with query parameters.
- Current params: `csv.x=yes`, `Datefrom=DD/Mon/YYYY`, `Dateto=DD/Mon/YYYY` or `now`, `SeriesCodes={code}`, `UsingCodes=Y`, `CSVF=TN`, `VPD=Y`, `VFD=N`.
- Starter mappings: Bank Rate/base rate `IUDBEDR`, SONIA `IUDSOIA`, sterling effective exchange rate index `XUDLBK67`.
- Response schema: CSV where the first column is date and series-code columns contain values. Parser normalizes dates and returns `date`, `value`, `series_code`, and raw row.
- Time alignment: infer date window from explicit years or article as-of date; use `Dateto` from context rather than always `now` for historical news.
- Adapter output: return series code, label, URL, and latest aligned observations. Mark human review if the claim mentions a UK series code not in the mapping.

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
