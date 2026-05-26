# Market Price Vendors

Source id: market_prices_vendor
Reference docs:
- Marketstack: https://marketstack.com/documentation
- Tiingo: https://www.tiingo.com/documentation/end-of-day
Authority tier: T3 supplemental
License tag: third_party_restricted

Use for:
- Latest quote, end-of-day price, and recent market-price checks from configured vendor APIs.
- Supplemental price evidence when the claim needs recent quotes and the project has a configured vendor key.

Do not use for:
- Reported financial statements, official regulatory facts, macro observations, or entity identity.
- Compliance-critical market data unless the organization has licensed the source for that use.

Important metadata:
- Preserve vendor, symbol, exchange, timestamp/date, price type, currency, adjustment policy, and API request URL or parameter summary.
- Treat different vendor values, delayed data, missing market calendars, and unclear adjustment policy as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say this source group covers supplemental latest/EOD prices.
- Load this detail when a claim is specifically about current price, quote, recent market value, or EOD price.
