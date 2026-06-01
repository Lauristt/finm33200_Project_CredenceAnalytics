# Historical Price Series

Source id: historical_prices
Authority tier: T3 supplemental
License tag: third_party_restricted

Reference docs:
- Financial Modeling Prep historical EOD: https://site.financialmodelingprep.com/developer/docs/stable/index-historical-price-eod-full
- Alpha Vantage TIME_SERIES_DAILY: https://www.alphavantage.co/documentation/#daily
- Finnhub stock candles: https://finnhub.io/docs/api/stock-candles
- FRED observations: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- Stooq historical/latest quote browser: https://stooq.com/db/h/

Use for:
- Daily price, return, drawdown, volatility, relative performance, record-high, closing-high, and price-action claims.
- Equity, ETF, equity-index, volatility-index, and equity-index-future claims when the claim is about price/return rather than fundamentals.

Do not use for:
- Reported financial statement metrics, supply/backlog metrics, guidance, macro observations, or regulatory facts.
- Compliance-critical official exchange data unless the organization has a licensed market-data source.
- Old-date price claims when only a latest quote is available.

Adapter retrieval order:
1. Alpha Vantage historical daily prices if `ALPHA_VANTAGE_API_KEY` exists.
2. Financial Modeling Prep historical EOD prices if `FMP_API_KEY` exists.
3. Finnhub stock candles if `FINNHUB_API_KEY` exists.
4. FRED daily index-level series for `SPX`, `NDQ`, and `DJIA` when `FRED_API_KEY` exists and vendor price APIs are unavailable.
5. Stooq historical CSV fallback when available. Some Stooq historical CSV downloads may require an API plan; if unavailable, do not treat latest quote as historical evidence.

Financial Modeling Prep API playbook:
- Env var: `FMP_API_KEY`
- Endpoint used by adapter: `GET https://financialmodelingprep.com/stable/historical-price-eod/full`
- Required params: `symbol`, `from`, `to`, `apikey`
- Example: `symbol=^GSPC&from=2026-01-01&to=2026-05-26&apikey=<FMP_API_KEY>`
- Expected response shape: a JSON object with `historical` list, or a JSON list depending on plan/version.
- Row fields consumed: `date`, `open`, `high`, `low`, `close`, `volume`; adjusted variants such as `adjOpen`, `adjHigh`, `adjLow`, `adjClose` may be used when regular OHLC values are missing.
- Symbol naming rules for major US indexes:
  - `SPX` claim target -> FMP `^GSPC`; ETF fallback `SPY`.
  - `NDQ` Nasdaq Composite claim target -> FMP `^IXIC`; ETF fallback `QQQ`.
  - `NDX` Nasdaq 100 claim target -> FMP `^NDX`; ETF fallback `QQQ`.
  - `DJIA` claim target -> FMP `^DJI`; ETF fallback `DIA`.
  - `RUT` claim target -> FMP `^RUT`; ETF fallback `IWM`.
  - `VIX` claim target -> FMP `^VIX`.

Alpha Vantage API playbook:
- Env var: `ALPHA_VANTAGE_API_KEY`
- Endpoint: `GET https://www.alphavantage.co/query`
- Required params used by adapter: `function=TIME_SERIES_DAILY`, `symbol`, `outputsize=full`, `apikey`
- Expected response key: `Time Series (Daily)`.
- Row fields consumed: `1. open`, `2. high`, `3. low`, `4. close`, `5. volume`.
- Free-tier limitations and historical depth can affect availability; keep provider notes in audit output.

Finnhub API playbook:
- Env var: `FINNHUB_API_KEY`
- Endpoint: `GET https://finnhub.io/api/v1/stock/candle`
- Required params: `symbol`, `resolution=D`, `from`, `to`, `token`
- `from` and `to` are UTC Unix timestamps.
- Expected response shape: `{ "s": "ok", "t": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...] }`.
- Row fields consumed by index: date from `t`, open from `o`, high from `h`, low from `l`, close from `c`, volume from `v`.

FRED index fallback playbook:
- Env var: `FRED_API_KEY`
- Endpoint: `GET https://api.stlouisfed.org/fred/series/observations`
- Required params: `series_id`, `observation_start`, `observation_end`, `api_key`, `file_type=json`
- Internal index mappings:
  - `SPX` -> `SP500`
  - `NDQ` -> `NASDAQCOM`
  - `DJIA` -> `DJIA`
- FRED provides index levels, not full OHLCV bars. The adapter stores each observation as a close-only price point so point changes and close-to-close returns can still be replayed.
- Do not use this fallback for Russell 2000 (`RUT`) unless a real Russell price series or licensed provider is configured.

Stooq playbook:
- Latest quote endpoint: `GET https://stooq.com/q/l/?s=<symbol>&f=sd2t2ohlcv&h&e=csv`
- Historical CSV endpoint used by adapter: `GET https://stooq.com/q/d/l/?s=<symbol>&d1=<YYYYMMDD>&d2=<YYYYMMDD>&i=d`
- Historical CSV fields consumed: `Date`, `Open`, `High`, `Low`, `Close`, `Volume`.
- Stooq symbol naming:
  - Indexes often use lowercase caret symbols such as `^spx`, `^dji`, `^ndq`.
  - US equities/ETFs use `.us` suffix, e.g. `spy.us`, `iwm.us`.
- Latest quotes are useful only for current-date/near-current quote claims. Do not use a latest quote to verify a claim whose inferred `as_of_date` is before the quote date.

Window rules:
- `Tuesday`, `session`, `today`, `yesterday`, or a daily move claim -> single-session context ending at inferred event date.
- `For the year`, `this year`, `YTD`, `year-to-date` -> January 1 of the event year through inferred as-of date.
- `recently`, `recent gains`, or `sharp gains` -> approximate one-month window.
- `recent months` -> approximate three-month window.
- Explicit lookbacks like `last 6 weeks` or `past 10 months` -> use the stated lookback.

Important metadata:
- Preserve provider, requested symbol, provider symbol, date window, observation date, open/high/low/close, adjusted close if used, volume, and API request URL or parameter summary.
- Preserve `window_label` and `window_source` in `raw` and evidence text.
- Treat missing historical series, provider entitlement/rate limits, unavailable dates, unclear adjustment policy, and vendor disagreement as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say this source group covers supplemental historical equity prices.
- Load this detail before retrieving price/return claims, especially when the claim requires index aliases, an event-date window, or a YTD calculation.
