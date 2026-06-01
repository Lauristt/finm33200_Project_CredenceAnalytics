# Market Price Vendors

Source id: market_prices_vendor
Reference docs:
- Marketstack: https://marketstack.com/documentation
- Tiingo: https://www.tiingo.com/documentation/end-of-day
- Financial Modeling Prep developer docs: https://site.financialmodelingprep.com/developer/docs
- Alpha Vantage documentation: https://www.alphavantage.co/documentation/
Authority tier: T3 supplemental
License tag: third_party_restricted

API playbook:
- Auth/env: latest/EOD quote group supports `MARKETSTACK_API_KEY`, `TIINGO_API_KEY`, and no-key Stooq. Historical-return claims should use `historical_prices`, which can use `ALPHA_VANTAGE_API_KEY`, `FMP_API_KEY`, `FINNHUB_API_KEY`, or Stooq CSV.
- Marketstack latest EOD: `GET https://api.marketstack.com/v1/eod/latest?access_key={key}&symbols={symbol}&limit=1`; fields include `date`, `close`, `volume`, `exchange`, and `symbol`.
- Tiingo daily prices: `GET https://api.tiingo.com/tiingo/daily/{symbol}/prices?startDate={YYYY-MM-DD}&token={key}`; fields include `date`, `close`, `adjClose`, and `volume`.
- Stooq latest quote: `GET https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv`; fields include `Date`, `Open`, `High`, `Low`, `Close`, and `Volume`.
- Symbol rules: internal index symbols are mapped per provider, for example `SPX -> ^GSPC/^spx/SPY`, `NDQ -> ^IXIC/^ndq/QQQ`, `DJIA -> ^DJI/^dji/DIA`, `RUT -> ^RUT/IWM`, and `VIX -> ^VIX/^vix`.
- Time alignment: latest quotes must not be used for old articles unless `published_at/as_of_date` confirms the quote date is not after the article context.
- Adapter output: return vendor, requested symbol, provider symbol, quote date, close, volume, and URL. Different vendor values or adjustment policies trigger human review.

Use for:
- Latest quote, end-of-day price, and recent market-price checks from configured vendor APIs.
- Supplemental price evidence when the claim needs recent quotes and the project has a configured vendor key.

Do not use for:
- Reported financial statements, official regulatory facts, macro observations, or entity identity.
- Compliance-critical market data unless the organization has licensed the source for that use.

Important metadata:
- Preserve vendor, symbol, exchange, timestamp/date, price type, currency, adjustment policy, and API request URL or parameter summary.
- Treat different vendor values, delayed data, missing market calendars, and unclear adjustment policy as human-review triggers.

Provider naming rules:
- Project-level index targets are normalized to internal symbols such as `SPX`, `NDQ`, `NDX`, `DJIA`, `RUT`, and `VIX`.
- Provider symbols differ by vendor. For example, S&P 500 can be `^GSPC` on FMP/Finnhub/Marketstack and `^spx` on Stooq.
- ETF fallbacks such as `SPY`, `QQQ`, `DIA`, and `IWM` are supplemental proxies, not the same thing as index-level official evidence.
- If the claim needs a historical return, prefer `historical_prices`; use this latest/EOD quote group only when the claim is about a current or latest quote.

Progressive-disclosure guidance:
- First-pass card should only say this source group covers supplemental latest/EOD prices.
- Load this detail when a claim is specifically about current price, quote, recent market value, or EOD price.
