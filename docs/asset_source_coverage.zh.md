# 跨资产数据源覆盖与测试种子

更新日期：2026-05-27

这个文件配合 `src/financial_credibility/asset_source_map.py` 和
`tests/test_asset_source_coverage.py` 使用。目标是让 agent 走固定闭环：

1. 从新闻或 memo 识别 entity / asset class。
2. 把 asset class 映射到 source、series id、endpoint hint 和 adapter status。
3. 进入 source selection 与 retrieval。
4. 用 coverage tests 发现 mapping 或 adapter 缺口。

## 当前结构化覆盖

| Asset class | 主要 source | 能取到的数据 | 当前状态 |
|---|---|---|---|
| single_name_equity | SEC, OpenFIGI, historical/vendor prices | XBRL fundamentals, filings, identifiers, price history | implemented |
| equity_index | historical/vendor prices | index/ETF price action, returns, record highs | implemented via supplemental market data |
| commodity | EIA, FRED | WTI, Brent, gasoline, natural gas, petroleum inventory, gold | implemented starter mapping |
| commodity_future / derivatives | CFTC COT, BIS | futures/options positioning, open interest, global derivatives statistics | CFTC implemented; BIS starter |
| rates | FRED, ECB, BOE | SOFR, Fed funds, Treasury yields, ECB policy rates, Bank Rate, SONIA | implemented starter mapping |
| credit | FRED, BIS, FINRA | HY/IG OAS, debt securities, TRACE/fixed-income datasets | FRED/BIS/FINRA starter implemented |
| fixed_income | FINRA, BIS, World Bank IDS | TRACE, corporate bond market breadth/sentiment, Treasury aggregates, debt securities, country debt | FINRA/BIS/WB implemented starter mapping |
| fx | FRED, ECB, BOE, IMF | major FX pairs, dollar index, EUR reference rates, sterling series | implemented starter mapping |
| macro_indicator | BLS, BEA, FRED, IMF, World Bank, ECB, BOE | CPI/PPI/labor, GDP/PCE/NIPA, WEO, WDI, HICP, UK macro | implemented starter mapping |

## 新闻种子

这些不是为了固定判断新闻真假，而是为了让 coverage benchmark 覆盖真实市场语言。

| 类别 | 近期新闻/官方 release 信号 | 测试里对应的 claim 类型 |
|---|---|---|
| Equity index | AP/Reuters 系报道在 2026-05-26 提到 S&P 500 和 Nasdaq 创收盘/历史新高。 | S&P 500 / Nasdaq record high -> equity_index -> historical_prices / market_prices_vendor |
| Single-name equity | Nvidia 2026-05 earnings/news flow 聚焦 AI demand、quarterly revenue、buyback/dividend。 | Nvidia revenue outlook / shares rallied -> single_name_equity -> SEC + price history |
| CPI / inflation | BLS 2026-05-12 发布 April 2026 CPI release。 | CPI/core CPI -> macro_indicator -> BLS `CUSR0000SA0` / `CUSR0000SA0L1E` |
| GDP / PCE | BEA GDP/PCE pages showed late-May 2026 release schedule. | GDP/PCE -> macro_indicator -> BEA NIPA table/line mapping |
| Oil / inventory | 2026-05 Reuters/EIA coverage repeatedly referenced crude inventory draws and WTI/Brent reaction. | WTI/EIA stockpiles -> commodity -> EIA `RWTC` / `WCESTUS1` |
| Gold / FX / rates | Reuters-linked coverage tied gold and dollar moves to Treasury yields and geopolitical risk. | gold, dollar/yen, Treasury yields -> FRED / CFTC / rates/FX mapping |
| Credit / fixed income | Fed May 2026 Financial Stability Report discussed high-yield spreads and corporate bond risk premia. | HY/IG OAS, corporate bond spreads -> FRED; TRACE/fixed-income market breadth -> FINRA |

Reference URLs used when seeding cases:

- https://apnews.com/article/71cc7b49f2ca3462a118878c93c75940
- https://www.investing.com/news/stock-market-news/sp-500-hits-record-closing-high-on-ai-optimism-micron-joins-1-trillion-club-4710656
- https://www.bls.gov/news.release/archives/cpi_05122026.htm
- https://www.bea.gov/data/gdp/gross-domestic-product
- https://bea.gov/data/personal-consumption-expenditures-price-index
- https://www.investing.com/news/commodities-news/us-crude-stockpiles-fall-79-million-barrels-eia-reports-93CH-4701729
- https://finance.yahoo.com/markets/currencies/articles/dollar-rides-rising-yields-largest-045936182.html
- https://www.federalreserve.gov/publications/files/financial-stability-report-20260508.pdf

## 大规模新闻 Benchmark

新增文件：

```text
src/financial_credibility/news_benchmark.py
tests/test_cross_asset_news_benchmark.py
```

当前 benchmark 有 30 条近期新闻/官方数据风格测试样例，覆盖：

```text
single_name_equity, equity_index, equity_index_future, fund_etf,
macro_indicator, rates, credit, fixed_income, commodity, commodity_future,
fx, derivatives
```

运行：

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_cross_asset_news_benchmark.py
```

它不会直接打 live API，而是检查四层是否接通：

1. entity extraction 能识别对应 asset class。
2. `asset_source_plan` 能把 asset class 映射到官方或结构化数据源。
3. `select_sources` / `route_sources` 能把 claim 推到候选 provider。
4. series mapping 能落到具体 series、dataset、SDMX key 或 endpoint hint。

这轮自测的 loop 结果：

| 阶段 | 结果 |
|---|---|
| 初始大样本 | 30 cases, 9 failed |
| 修补内容 | index/futures/ETF OHLCV mapping、BLS unemployment/PPI、FRED Brent/WTI、EIA gas、BIS banking、ECB HICP、官方 acronym stopwords |
| 当前结果 | 30 cases, 0 failed |

## 当前明确缺口

- FINRA: `.env` 里已经配置 `FINRA_CLIENT_ID` / `FINRA_CLIENT_SECRET`，starter adapter 已能走 OAuth2 token flow 和 Query API。live smoke 证明 credential 可用；formal fixed-income dataset 当前返回 403，说明还需要 FINRA entitlement。后续缺口是更细的 dataset discovery、entitlement handling、async jobs、字段级 mapping。
- Live API smoke: `CREDIBILITY_RUN_LIVE_API_TESTS=true PYTHONPATH=src python3 -m pytest -q tests/test_live_asset_source_smoke.py` 当前结果是 2 passed, 1 skipped。通过的是 keyed official adapters 与 no-key global adapters；skip 的是 FINRA fixed-income entitlement。
- Equity vendor keys: Alpha Vantage/Finnhub/FMP/Marketstack/Tiingo 为空时，price/fundamentals 会更多依赖 Stooq 或 supplemental fallback。
- SDMX discovery: ECB/BIS/IMF starter mapping 已有，但还需要 dataflow/dimension discovery cache，避免硬写太多 key。
- Series expansion: FRED/BLS/BEA/EIA starter set 已覆盖主路径，下一步要继续扩 alias、frequency、unit 和 release/vintage metadata。
