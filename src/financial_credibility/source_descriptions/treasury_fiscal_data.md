# U.S. Treasury Fiscal Data

Source id: treasury_fiscal_data
Official docs: https://fiscaldata.treasury.gov/api-documentation/
Example dataset: https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/
Authority tier: T1 official primary
License tag: public_official

Official description summary:
- Fiscal Data provides machine-readable U.S. Treasury datasets with APIs, data previews, metadata, and data dictionaries.
- Dataset pages expose fields, descriptions, units, date ranges, release cadence, and API quick guides.
- It is the default primary evidence source for U.S. federal fiscal, debt, and Treasury-published values.

Use for:
- U.S. federal debt, debt held by the public, intragovernmental holdings, Daily Treasury Statement, Monthly Statement of the Public Debt, rates, auctions, receipts, and fiscal datasets.
- Claims about Treasury-published federal fiscal metrics and record-date-specific values.

Do not use for:
- Company fundamentals, SEC filing facts, equity market prices, or non-US government fiscal series.
- Broad macro claims better represented by FRED/BEA/BLS unless the claim is specifically Treasury fiscal data.

Important metadata:
- Preserve endpoint/dataset, table, record_date, field names, value, unit/currency, last-updated information when available, and query parameters.
- Fiscal Data endpoints commonly support field selection, filters, sorting, format, and pagination. Keep the exact request in the audit trace.
- Treat dataset choice ambiguity, restatement flags, units in millions vs dollars, and stale record dates as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say this source covers Treasury fiscal and debt datasets.
- Load this detail for national debt, public debt, deficit/fiscal, Treasury rates, auctions, and Daily Treasury Statement claims.
