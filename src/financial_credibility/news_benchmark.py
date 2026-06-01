"""Cross-asset recent-news benchmark cases for source-mapping QA."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .asset_source_map import asset_source_plan
from .config import ToolkitConfig
from .entity_extraction import extract_entities_from_memo
from .routing import route_sources
from .source_selection import candidate_sources_for_claim_with_options


@dataclass(frozen=True)
class CrossAssetNewsCase:
    """One recent-news-style case with expected routing outcomes."""

    case_id: str
    asset_classes: tuple[str, ...]
    claim: str
    expected_sources: tuple[str, ...]
    expected_series: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CROSS_ASSET_NEWS_CASES: tuple[CrossAssetNewsCase, ...] = (
    CrossAssetNewsCase(
        case_id="equity_nvda_revenue_buyback",
        asset_classes=("single_name_equity",),
        claim="Nvidia forecast quarterly revenue above estimates and announced an $80 billion share buyback.",
        expected_sources=("sec_company_facts", "sec_recent_filings"),
        expected_series=("us-gaap concept map",),
        source_urls=("https://www.investing.com/news/stock-market-news/nvidia-forecasts-quarterly-revenue-above-estimates-announces-80-billion-share-buyback-4702363",),
    ),
    CrossAssetNewsCase(
        case_id="equity_micron_rally_market_cap",
        asset_classes=("single_name_equity",),
        claim="Micron shares surged as AI optimism pushed the company toward a $1 trillion market value.",
        expected_sources=("historical_prices", "market_prices_vendor"),
        expected_series=("ticker OHLCV",),
        source_urls=("https://apnews.com/article/71cc7b49f2ca3462a118878c93c75940",),
    ),
    CrossAssetNewsCase(
        case_id="equity_index_spx_nasdaq_record_high",
        asset_classes=("equity_index",),
        claim="The S&P 500 and Nasdaq hit record closing highs on AI optimism.",
        expected_sources=("historical_prices", "market_prices_vendor"),
        expected_series=("index OHLCV",),
        source_urls=("https://www.marketscreener.com/news/s-p-500-nasdaq-hit-record-closing-highs-on-ai-optimism-ce7f5ad2dc88f020",),
    ),
    CrossAssetNewsCase(
        case_id="equity_index_future_record_futures",
        asset_classes=("equity_index_future",),
        claim="S&P 500 futures and Nasdaq futures rose to record highs as Nvidia shares jumped.",
        expected_sources=("historical_prices",),
        expected_series=("futures OHLCV",),
        source_urls=("https://www.investing.com/news/stock-market-news/sp-500-nasdaq-futures-rise-to-new-highs-as-nvidia-jumps-4687631",),
    ),
    CrossAssetNewsCase(
        case_id="fund_etf_hyg_lqd_credit",
        asset_classes=("fund_etf", "credit"),
        claim="HYG and LQD are useful ETF proxies when checking whether high-yield and investment-grade credit markets moved.",
        expected_sources=("historical_prices", "market_prices_vendor", "fred"),
        expected_series=("ticker OHLCV", "BAMLH0A0HYM2", "BAMLC0A0CM"),
        source_urls=("https://www.federalreserve.gov/publications/files/financial-stability-report-20260508.pdf",),
    ),
    CrossAssetNewsCase(
        case_id="macro_bls_cpi_core",
        asset_classes=("macro_indicator",),
        claim="BLS reported that CPI rose in April 2026 and core CPI inflation also increased.",
        expected_sources=("bls_api", "fred"),
        expected_series=("CUSR0000SA0", "CUSR0000SA0L1E"),
        source_urls=("https://www.bls.gov/news.release/archives/cpi_05122026.htm",),
    ),
    CrossAssetNewsCase(
        case_id="macro_bls_jobs_payrolls",
        asset_classes=("macro_indicator",),
        claim="The April 2026 jobs report said nonfarm payrolls rose and the unemployment rate held steady.",
        expected_sources=("bls_api", "fred"),
        expected_series=("CES0000000001", "LNS14000000"),
        source_urls=("https://finance.yahoo.com/economy/articles/april-2026-jobs-report-u-123736868.html",),
    ),
    CrossAssetNewsCase(
        case_id="macro_bls_ppi_tariff",
        asset_classes=("macro_indicator",),
        claim="Producer prices and PPI data matter for checking inflation pressure after hotter-than-expected producer price data.",
        expected_sources=("bls_api", "fred"),
        expected_series=("WPUFD4", "PPIACO"),
        source_urls=("https://www.investing.com/news/stock-market-news/sp-500-nasdaq-futures-rise-to-new-highs-as-nvidia-jumps-4687631",),
    ),
    CrossAssetNewsCase(
        case_id="macro_bea_gdp_q1",
        asset_classes=("macro_indicator",),
        claim="BEA's advance estimate showed real GDP growth for the first quarter of 2026.",
        expected_sources=("bea_api", "fred"),
        expected_series=("NIPA T10101 line 1",),
        source_urls=("https://www.bea.gov/news/2026/gdp-advance-estimate-1st-quarter-2026",),
    ),
    CrossAssetNewsCase(
        case_id="macro_bea_pce_core",
        asset_classes=("macro_indicator",),
        claim="The BEA PCE price index and core PCE inflation should be checked from BEA data.",
        expected_sources=("bea_api", "fred"),
        expected_series=("NIPA T20804 line 1", "PCEPILFE"),
        source_urls=("https://bea.gov/data/personal-consumption-expenditures-price-index",),
    ),
    CrossAssetNewsCase(
        case_id="rates_30y_treasury",
        asset_classes=("rates",),
        claim="The 30-year Treasury yield rose as rates markets sold off.",
        expected_sources=("fred",),
        expected_series=("DGS30",),
        source_urls=("https://finance.yahoo.com/markets/currencies/articles/dollar-rides-rising-yields-largest-045936182.html",),
    ),
    CrossAssetNewsCase(
        case_id="rates_sofr_fedfunds",
        asset_classes=("rates",),
        claim="SOFR and the effective federal funds rate are core short-term rates for checking US money-market claims.",
        expected_sources=("fred",),
        expected_series=("SOFR", "FEDFUNDS"),
        source_urls=("https://fred.stlouisfed.org/docs/api/fred/",),
    ),
    CrossAssetNewsCase(
        case_id="credit_fed_fsr_spreads",
        asset_classes=("credit",),
        claim="The Fed Financial Stability Report said corporate bond spreads and high-yield spreads remained low by historical standards.",
        expected_sources=("fred",),
        expected_series=("BAMLH0A0HYM2", "BAMLC0A0CM"),
        source_urls=("https://www.federalreserve.gov/publications/files/financial-stability-report-20260508.pdf",),
    ),
    CrossAssetNewsCase(
        case_id="fixed_income_finra_trace",
        asset_classes=("fixed_income",),
        claim="FINRA TRACE fixed income data should be used to check corporate bond trading volume and market breadth.",
        expected_sources=("finra_query_api",),
        expected_series=("FINRA group/name dataset",),
        source_urls=("https://developer.finra.org/docs/api-explorer/query_api-fixed_income-corporate_debt_market_breadth",),
    ),
    CrossAssetNewsCase(
        case_id="fixed_income_bis_debt_securities",
        asset_classes=("fixed_income",),
        claim="BIS international debt securities statistics can check global bond issuance and debt securities outstanding.",
        expected_sources=("bis_data_portal",),
        expected_series=("WS_DEBT_SEC2_PUB",),
        source_urls=("https://data.bis.org/",),
    ),
    CrossAssetNewsCase(
        case_id="commodity_eia_wti_inventory",
        asset_classes=("commodity",),
        claim="WTI crude oil prices reacted after EIA reported a large draw in US crude stockpiles.",
        expected_sources=("eia_api", "fred"),
        expected_series=("RWTC", "WCESTUS1"),
        source_urls=("https://www.investing.com/news/commodities-news/us-crude-stockpiles-fall-79-million-barrels-eia-reports-93CH-4701729",),
    ),
    CrossAssetNewsCase(
        case_id="commodity_brent_oil",
        asset_classes=("commodity",),
        claim="Brent crude oil prices moved as traders assessed US crude inventories and geopolitical risk.",
        expected_sources=("eia_api", "fred"),
        expected_series=("RBRTE", "DCOILBRENTEU"),
        source_urls=("https://www.investing.com/news/commodities-news/us-crude-stockpiles-fall-79-million-barrels-eia-reports-93CH-4701729",),
    ),
    CrossAssetNewsCase(
        case_id="commodity_gold_yields",
        asset_classes=("commodity", "rates"),
        claim="Gold prices were shaped by Treasury yields, the dollar, and geopolitical risk.",
        expected_sources=("fred",),
        expected_series=("GOLDAMGBD228NLBM", "DGS10", "DTWEXBGS"),
        source_urls=("https://dhbna.com/gold-price-and-geopolitical-risk-may-14-2026/",),
    ),
    CrossAssetNewsCase(
        case_id="commodity_natural_gas",
        asset_classes=("commodity",),
        claim="Henry Hub natural gas prices are an EIA/FRED energy commodity check.",
        expected_sources=("eia_api", "fred"),
        expected_series=("RNGWHHD", "DHHNGSP"),
        source_urls=("https://www.eia.gov/opendata/documentation.php",),
    ),
    CrossAssetNewsCase(
        case_id="commodity_future_cftc_gold",
        asset_classes=("commodity_future", "derivatives"),
        claim="CFTC COT data can check gold futures open interest and managed money positioning.",
        expected_sources=("cftc_cot",),
        expected_series=("CFTC PRE 6dca-aqww",),
        source_urls=("https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",),
    ),
    CrossAssetNewsCase(
        case_id="fx_dollar_yen_yields",
        asset_classes=("fx", "rates"),
        claim="The dollar strengthened against the yen as Treasury yields surged.",
        expected_sources=("fred",),
        expected_series=("DEXJPUS", "DGS10"),
        source_urls=("https://finance.yahoo.com/markets/currencies/articles/dollar-rides-rising-yields-largest-045936182.html",),
    ),
    CrossAssetNewsCase(
        case_id="fx_euro_reference_rate",
        asset_classes=("fx",),
        claim="ECB euro reference rates should be used to check EUR/USD exchange-rate claims.",
        expected_sources=("ecb_data_portal", "fred"),
        expected_series=("EXR SDMX key", "DEXUSEU"),
        source_urls=("https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",),
    ),
    CrossAssetNewsCase(
        case_id="rates_ecb_deposit",
        asset_classes=("rates",),
        claim="The ECB deposit facility rate remained at 2.00 percent in April 2026.",
        expected_sources=("ecb_data_portal",),
        expected_series=("FM SDMX policy-rate key",),
        source_urls=("https://www.ecb.europa.eu/home/html/index.ct.html",),
    ),
    CrossAssetNewsCase(
        case_id="rates_boe_bank_rate",
        asset_classes=("rates", "fx"),
        claim="The Bank of England Bank Rate stayed at 3.75 percent while sterling moved.",
        expected_sources=("bank_of_england",),
        expected_series=("IUDBEDR / IUDSOIA",),
        source_urls=("https://www.bankofengland.co.uk/boeapps/database/",),
    ),
    CrossAssetNewsCase(
        case_id="macro_imf_weo",
        asset_classes=("macro_indicator",),
        claim="IMF WEO data should be used to check US GDP growth and inflation forecasts.",
        expected_sources=("imf_data_api",),
        expected_series=("WEO country.indicator.frequency key",),
        source_urls=("https://www.imf.org/en/Data",),
    ),
    CrossAssetNewsCase(
        case_id="macro_world_bank_wdi",
        asset_classes=("macro_indicator",),
        claim="World Bank WDI can check China GDP and population data from 2015 to 2023.",
        expected_sources=("world_bank_indicators",),
        expected_series=("NY.GDP.MKTP.CD / indicator id",),
        source_urls=("https://api.worldbank.org/v2/country/CN/indicator/NY.GDP.MKTP.CD?format=json&date=2015:2023",),
    ),
    CrossAssetNewsCase(
        case_id="derivatives_bis_otc",
        asset_classes=("derivatives",),
        claim="BIS OTC derivatives statistics should be used to check interest-rate derivatives and FX derivatives outstanding.",
        expected_sources=("bis_data_portal",),
        expected_series=("BIS derivatives dataflow",),
        source_urls=("https://data.bis.org/topics/OTC_DER",),
    ),
    CrossAssetNewsCase(
        case_id="derivatives_cftc_fx_positioning",
        asset_classes=("derivatives", "fx"),
        claim="CFTC COT reports can check currency futures positioning and open interest in dollar and yen contracts.",
        expected_sources=("cftc_cot",),
        expected_series=("CFTC PRE 6dca-aqww",),
        source_urls=("https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",),
    ),
    CrossAssetNewsCase(
        case_id="global_macro_bis_banking",
        asset_classes=("macro_indicator", "fixed_income"),
        claim="BIS international banking statistics can check cross-border banking claims and global liquidity indicators.",
        expected_sources=("bis_data_portal",),
        expected_series=("BIS locational banking statistics",),
        source_urls=("https://www.bis.org/statistics/rppb2604.htm",),
    ),
    CrossAssetNewsCase(
        case_id="euro_macro_ecb_hicp",
        asset_classes=("macro_indicator",),
        claim="ECB HICP data can check euro area inflation after the May 2026 financial stability review.",
        expected_sources=("ecb_data_portal",),
        expected_series=("Euro area HICP annual rate",),
        source_urls=("https://www.ecb.europa.eu/press/financial-stability-publications/fsr/html/ecb.fsr202605~50566915a7.en.html",),
    ),
)


def benchmark_cases() -> list[dict[str, Any]]:
    """Return all benchmark cases as JSON-compatible dicts."""
    return [case.to_dict() for case in CROSS_ASSET_NEWS_CASES]


def evaluate_news_case(case: CrossAssetNewsCase, config: ToolkitConfig | None = None) -> dict[str, Any]:
    """Evaluate extraction, routing, source selection, and series mapping for one case."""
    cfg = config or ToolkitConfig(enable_ticker_universe_filter=False)
    extraction = extract_entities_from_memo(case.claim, cfg)
    plan = asset_source_plan(case.claim, extraction.get("entities", []), include_planned=True)
    candidates = candidate_sources_for_claim_with_options(case.claim, top_k=16, include_planned=True)
    route = route_sources(case.claim, official_only=False)
    source_ids = set(plan.get("source_ids", []))
    source_ids.update(item.get("source_id") for item in candidates)
    source_ids.update(route.get("routes", []))
    series_ids = {item.get("source_series_id") for item in plan.get("series_mappings", [])}
    assets = set(extraction.get("asset_classes", [])) | set(plan.get("asset_classes", []))
    return {
        "case": case.to_dict(),
        "extracted_asset_classes": sorted(assets),
        "source_ids": sorted(str(item) for item in source_ids if item),
        "series_ids": sorted(str(item) for item in series_ids if item),
        "missing_asset_classes": sorted(set(case.asset_classes) - assets),
        "missing_sources": sorted(set(case.expected_sources) - {str(item) for item in source_ids if item}),
        "missing_series": sorted(set(case.expected_series) - {str(item) for item in series_ids if item}),
        "entity_count": len(extraction.get("entities", [])),
        "candidate_count": len(candidates),
    }


def evaluate_news_benchmark(config: ToolkitConfig | None = None) -> dict[str, Any]:
    """Evaluate all cross-asset news benchmark cases."""
    evaluations = [evaluate_news_case(case, config=config) for case in CROSS_ASSET_NEWS_CASES]
    failed = [
        item
        for item in evaluations
        if item["missing_asset_classes"] or item["missing_sources"] or item["missing_series"]
    ]
    covered_assets = sorted({asset for item in evaluations for asset in item["case"]["asset_classes"]})
    return {
        "case_count": len(evaluations),
        "failed_count": len(failed),
        "covered_asset_classes": covered_assets,
        "evaluations": evaluations,
        "failed_cases": failed,
    }
