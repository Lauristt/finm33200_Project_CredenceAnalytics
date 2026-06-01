# World Bank Indicators API

Source id: world_bank_indicators
Official docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
Terms: https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets
Authority tier: T2 official/international statistics
License tag: cc_by
Adapter status: implemented

Official description summary:
- The World Bank Indicators API provides programmatic access to nearly 16,000 time-series indicators across many databases.
- It includes databases such as World Development Indicators and International Debt Statistics.
- World Bank datasets are generally available under CC BY 4.0 unless specifically labeled otherwise.

Use for:
- Long-run country indicators, development metrics, international debt, poverty, population, and broad country-level macro comparisons.
- Claims where World Bank indicator IDs provide clear reproducible evidence.
- Direct v2 calls such as `/country/CN/indicator/NY.GDP.MKTP.CD?format=json&date=2015:2023`.

Do not use for:
- Company financial statement claims, SEC filings, market prices, or security identity.
- Cases where a direct national statistical agency is required.

Important metadata:
- Preserve country code, indicator ID, source/database ID, date, value, unit/scale if available, topic, pagination, and API URL.
- Treat third-party indicator exceptions, missing values, revision differences, and database/source ambiguity as human-review triggers.

Authentication:
- The Indicators API v2 does not require an API key or token.
- Use `WORLD_BANK_BASE_URL=https://api.worldbank.org/v2` unless testing against a proxy.

API playbook:
- Auth/env: no key. Base URL is `WORLD_BANK_BASE_URL=https://api.worldbank.org/v2`.
- Current endpoint pattern: `GET {WORLD_BANK_BASE_URL}/country/{country}/indicator/{indicator}`.
- Current params: `format=json`; use `date=YYYY:YYYY` and `per_page=500` for explicit ranges, otherwise `MRV=5`.
- Starter country mapping: `US`, `CN`, `JP`, `GB`, `DE`, `FR`, `IN`, `BR`, `EMU`, `WLD`, and `all`.
- Starter indicator mapping: GDP `NY.GDP.MKTP.CD`, population `SP.POP.TOTL`, inflation `FP.CPI.TOTL.ZG`, unemployment `SL.UEM.TOTL.ZS`, external debt `DT.DOD.DECT.CD`, current account `BN.CAB.XOKA.CD`, poverty `SI.POV.DDAY`.
- Response schema: JSON array `[metadata, rows]`; rows include `indicator`, `country`, `countryiso3code`, `date`, `value`, `unit`, and `obs_status`.
- Adapter output: return country, indicator, pagination metadata, and non-null observations. Missing values or wrong country aggregation should be human review, not contradiction.

Progressive-disclosure guidance:
- First-pass card should only say World Bank Indicators covers country-level time-series indicators.
- Load this detail for WDI, country comparisons, development, international debt, or long-run macro indicators.
