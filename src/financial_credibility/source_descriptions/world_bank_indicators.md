# World Bank Indicators API

Source id: world_bank_indicators
Official docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
Terms: https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets
Authority tier: T2 official/international statistics
License tag: cc_by
Adapter status: planned

Official description summary:
- The World Bank Indicators API provides programmatic access to nearly 16,000 time-series indicators across many databases.
- It includes databases such as World Development Indicators and International Debt Statistics.
- World Bank datasets are generally available under CC BY 4.0 unless specifically labeled otherwise.

Use for:
- Long-run country indicators, development metrics, international debt, poverty, population, and broad country-level macro comparisons.
- Claims where World Bank indicator IDs provide clear reproducible evidence.

Do not use for:
- Company financial statement claims, SEC filings, market prices, or security identity.
- Cases where a direct national statistical agency is required.

Important metadata:
- Preserve country code, indicator ID, source/database ID, date, value, unit/scale if available, topic, pagination, and API URL.
- Treat third-party indicator exceptions, missing values, revision differences, and database/source ambiguity as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say World Bank Indicators covers country-level time-series indicators.
- Load this detail for WDI, country comparisons, development, international debt, or long-run macro indicators.

