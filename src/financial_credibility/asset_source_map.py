"""Asset-class to data-source coverage maps used by agents and tests."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .asset_universe import normalize_asset_class
from .models import LicenseTag, SourceTier
from .price_history import needs_historical_price_data
from .routing import route_sources


@dataclass(frozen=True)
class DataSourceDescription:
    """Structured description of what a source can provide."""

    source_id: str
    provider_name: str
    authority_tier: SourceTier
    license_tag: LicenseTag
    asset_classes: tuple[str, ...]
    data_available: tuple[str, ...]
    identifiers: tuple[str, ...]
    time_axis: str
    adapter_status: str
    required_env: tuple[str, ...] = ()
    no_key: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeriesMapping:
    """One claim/asset hint mapped to a source series, endpoint, or dataset."""

    mapping_id: str
    asset_class: str
    source_id: str
    provider_name: str
    topic: str
    aliases: tuple[str, ...]
    source_series_id: str
    endpoint_hint: str
    extraction_fields: tuple[str, ...]
    required_env: tuple[str, ...] = ()
    adapter_status: str = "implemented"
    priority: int = 50
    notes: tuple[str, ...] = ()


DATA_SOURCE_DESCRIPTIONS: tuple[DataSourceDescription, ...] = (
    DataSourceDescription(
        source_id="sec_company_facts",
        provider_name="sec_company_facts",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("single_name_equity",),
        data_available=(
            "US public-company XBRL facts",
            "revenue, sales, net income, EPS, cash flow, assets, liabilities, debt",
            "fiscal-period values with filing date, form, taxonomy concept, unit, and frame metadata",
        ),
        identifiers=("ticker", "CIK", "SEC accession context"),
        time_axis="fiscal period plus SEC filing date",
        adapter_status="implemented",
        required_env=("SEC_USER_AGENT",),
        no_key=True,
        notes=("Primary source for reported US issuer fundamentals.",),
    ),
    DataSourceDescription(
        source_id="sec_recent_filings",
        provider_name="sec_recent_filings",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("single_name_equity",),
        data_available=("10-K, 10-Q, 8-K, and filing metadata", "filing dates, accession numbers, and official filing URLs"),
        identifiers=("ticker", "CIK", "accession number"),
        time_axis="filing date",
        adapter_status="implemented",
        required_env=("SEC_USER_AGENT",),
        no_key=True,
        notes=("Use for filing/event context and links to source documents.",),
    ),
    DataSourceDescription(
        source_id="fred",
        provider_name="fred",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        asset_classes=("macro_indicator", "rates", "credit", "commodity", "fx", "equity_index"),
        data_available=(
            "FRED/ALFRED economic time series",
            "SOFR, Treasury yields, fed funds, CPI, PCE, GDP, payrolls, unemployment",
            "HY/IG OAS, WTI, Brent, gold, natural gas, major FX, and broad dollar index",
        ),
        identifiers=("series_id",),
        time_axis="observation date and optional realtime/vintage date",
        adapter_status="implemented",
        required_env=("FRED_API_KEY",),
        notes=("Fast broad macro/rates/credit/FX/commodity coverage; prefer direct official agency APIs when available.",),
    ),
    DataSourceDescription(
        source_id="bls_api",
        provider_name="bls_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("macro_indicator",),
        data_available=("CPI and core CPI", "PPI", "payrolls, unemployment, wages, JOLTS, and other BLS survey series"),
        identifiers=("BLS series id",),
        time_axis="year/period such as 2026-M04",
        adapter_status="implemented",
        required_env=("BLS_API_KEY",),
        notes=("Registration key is recommended; public API can work at lower limits without it.",),
    ),
    DataSourceDescription(
        source_id="bea_api",
        provider_name="bea_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("macro_indicator",),
        data_available=("GDP, NIPA, PCE, personal income", "industry, regional, international, and input-output accounts"),
        identifiers=("dataset", "table", "line number", "frequency"),
        time_axis="monthly, quarterly, or annual BEA time period",
        adapter_status="implemented",
        required_env=("BEA_API_KEY",),
        notes=("Starter adapter covers key NIPA table/line mappings; discovery cache should expand table coverage.",),
    ),
    DataSourceDescription(
        source_id="eia_api",
        provider_name="eia_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("commodity",),
        data_available=("WTI and Brent spot prices", "gasoline", "natural gas", "petroleum inventory and energy-balance routes"),
        identifiers=("APIv2 route", "series facet", "frequency"),
        time_axis="daily, weekly, monthly, or annual period",
        adapter_status="implemented",
        required_env=("EIA_API_KEY",),
        notes=("Primary source for official US energy statistics, not exchange settlement prices.",),
    ),
    DataSourceDescription(
        source_id="cftc_cot",
        provider_name="cftc_cot",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("commodity_future", "equity_index_future", "rates", "fx", "derivatives"),
        data_available=("Commitments of Traders futures/options positioning", "open interest", "trader categories"),
        identifiers=("CFTC PRE dataset id", "market/exchange name", "report date"),
        time_axis="weekly report date",
        adapter_status="implemented",
        required_env=("CFTC_APP_TOKEN",),
        no_key=True,
        notes=("App token is optional but useful for quota/identity.",),
    ),
    DataSourceDescription(
        source_id="finra_query_api",
        provider_name="finra_query_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        asset_classes=("fixed_income", "single_name_equity", "credit"),
        data_available=("TRACE/fixed-income regulatory datasets", "equity regulatory data", "registration datasets"),
        identifiers=("dataset group", "dataset name", "filters", "fields"),
        time_axis="dataset-specific trade, report, or publication timestamp",
        adapter_status="implemented",
        required_env=("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET"),
        notes=("Uses OAuth client credentials; fixed-income dataset access still depends on FINRA entitlements.",),
    ),
    DataSourceDescription(
        source_id="openfigi",
        provider_name="openfigi",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.UNKNOWN,
        asset_classes=("single_name_equity", "fund_etf", "fixed_income"),
        data_available=("FIGI, composite FIGI, ticker, name, security type, market sector", "ISIN/CUSIP/SEDOL mappings"),
        identifiers=("ticker", "FIGI", "ISIN", "CUSIP", "SEDOL"),
        time_axis="current identifier mapping",
        adapter_status="implemented",
        required_env=("OPENFIGI_API_KEY",),
        no_key=True,
        notes=("Key is optional but recommended for rate limits.",),
    ),
    DataSourceDescription(
        source_id="ecb_data_portal",
        provider_name="ecb_data_portal",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("macro_indicator", "rates", "fx"),
        data_available=("ECB policy rates", "EUR FX reference rates", "HICP", "banking, payments, monetary statistics"),
        identifiers=("dataflow", "SDMX key"),
        time_axis="SDMX observation period",
        adapter_status="implemented",
        no_key=True,
    ),
    DataSourceDescription(
        source_id="bis_data_portal",
        provider_name="bis_data_portal",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("fixed_income", "credit", "macro_indicator", "derivatives"),
        data_available=("international banking", "debt securities", "credit-to-GDP", "global liquidity", "derivatives statistics"),
        identifiers=("BIS dataflow", "SDMX key"),
        time_axis="SDMX observation period",
        adapter_status="implemented",
        no_key=True,
    ),
    DataSourceDescription(
        source_id="imf_data_api",
        provider_name="imf_data_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        asset_classes=("macro_indicator", "fx"),
        data_available=("WEO", "BOP", "reserves", "fiscal", "inflation", "cross-country macro datasets"),
        identifiers=("agency", "dataflow", "SDMX key", "country"),
        time_axis="SDMX observation period",
        adapter_status="implemented",
        no_key=True,
        notes=("Public SDMX API is no-key; restricted iData access uses OAuth, not an API key.",),
    ),
    DataSourceDescription(
        source_id="world_bank_indicators",
        provider_name="world_bank_indicators",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.CC_BY,
        asset_classes=("macro_indicator", "fixed_income"),
        data_available=("WDI indicators", "International Debt Statistics", "country development and macro indicators"),
        identifiers=("country code", "indicator id"),
        time_axis="calendar year",
        adapter_status="implemented",
        no_key=True,
    ),
    DataSourceDescription(
        source_id="bank_of_england",
        provider_name="bank_of_england",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        asset_classes=("rates", "fx", "macro_indicator", "credit"),
        data_available=("Bank Rate", "SONIA", "GBP FX/effective exchange rates", "UK monetary and credit statistics"),
        identifiers=("IADB series code",),
        time_axis="IADB observation date",
        adapter_status="implemented",
        no_key=True,
    ),
    DataSourceDescription(
        source_id="historical_prices",
        provider_name="historical_prices",
        authority_tier=SourceTier.T3,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        asset_classes=("single_name_equity", "fund_etf", "equity_index", "volatility_index", "equity_index_future"),
        data_available=("daily OHLCV price history", "returns, volatility, drawdown, relative performance"),
        identifiers=("ticker", "date window"),
        time_axis="trading date",
        adapter_status="implemented",
        required_env=("ALPHA_VANTAGE_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY"),
        no_key=True,
        notes=("Stooq fallback is no-key; vendor keys improve coverage.",),
    ),
    DataSourceDescription(
        source_id="market_prices_vendor",
        provider_name="market_prices_vendor",
        authority_tier=SourceTier.T3,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        asset_classes=("single_name_equity", "fund_etf", "equity_index", "volatility_index", "equity_index_future"),
        data_available=("latest quote", "end-of-day price checks"),
        identifiers=("ticker",),
        time_axis="market timestamp or EOD date",
        adapter_status="implemented",
        required_env=("MARKETSTACK_API_KEY", "TIINGO_API_KEY"),
        no_key=True,
        notes=("Use as supplemental market data, not as official issuer evidence.",),
    ),
)


SERIES_MAPPINGS: tuple[SeriesMapping, ...] = (
    # Equity and identifiers.
    SeriesMapping(
        "sec_revenue",
        "single_name_equity",
        "sec_company_facts",
        "sec_company_facts",
        "reported revenue and financial-statement metrics",
        ("revenue", "sales", "eps", "net income", "cash flow", "assets", "debt", "margin"),
        "us-gaap concept map",
        "data.sec.gov/api/xbrl/companyfacts/CIK##########.json",
        ("concept", "period", "value", "unit", "filed", "form"),
        required_env=("SEC_USER_AGENT",),
        priority=95,
    ),
    SeriesMapping(
        "equity_price_history",
        "single_name_equity",
        "historical_prices",
        "historical_prices",
        "stock price, return, volatility, drawdown",
        (
            "stock price",
            "share price",
            "return",
            "fell",
            "dropped",
            "declined",
            "gained",
            "gains",
            "rose",
            "jumped",
            "surged",
            "rally",
            "rallied",
            "selloff",
            "drawdown",
            "record high",
            "closing high",
        ),
        "ticker OHLCV",
        "Alpha Vantage/FMP/Finnhub/Stooq historical price endpoints",
        ("date", "open", "high", "low", "close", "volume"),
        required_env=("ALPHA_VANTAGE_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY"),
        priority=70,
    ),
    SeriesMapping(
        "equity_index_history",
        "equity_index",
        "historical_prices",
        "historical_prices",
        "equity index price history",
        ("s&p 500", "spx", "nasdaq", "nasdaq 100", "dow jones", "russell 2000", "record high", "closing high", "index return"),
        "index OHLCV",
        "Index/ETF proxy historical price endpoints",
        ("date", "open", "high", "low", "close", "volume"),
        required_env=("ALPHA_VANTAGE_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY"),
        priority=78,
    ),
    SeriesMapping(
        "equity_index_future_history",
        "equity_index_future",
        "historical_prices",
        "historical_prices",
        "equity index futures price history",
        ("s&p 500 futures", "spx futures", "nasdaq futures", "nasdaq 100 futures", "e-mini s&p", "e-mini nasdaq", "es futures", "nq futures"),
        "futures OHLCV",
        "Futures or ETF proxy historical price endpoints",
        ("date", "open", "high", "low", "close", "volume"),
        required_env=("ALPHA_VANTAGE_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY"),
        priority=77,
    ),
    SeriesMapping(
        "fund_etf_history",
        "fund_etf",
        "historical_prices",
        "historical_prices",
        "ETF price history",
        ("etf", "spy", "qqq", "hyg", "lqd", "tlt", "gld", "uso"),
        "ticker OHLCV",
        "ETF historical price endpoints",
        ("date", "open", "high", "low", "close", "volume"),
        required_env=("ALPHA_VANTAGE_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY"),
        priority=80,
    ),
    SeriesMapping(
        "openfigi_identity",
        "single_name_equity",
        "openfigi",
        "openfigi",
        "instrument identity mapping",
        ("figi", "isin", "cusip", "sedol", "ticker mapping", "instrument identity"),
        "FIGI mapping",
        "api.openfigi.com/v3/mapping",
        ("figi", "compositeFIGI", "ticker", "name", "securityType", "marketSector"),
        required_env=("OPENFIGI_API_KEY",),
        priority=80,
    ),
    # Macro and labor.
    SeriesMapping("bls_cpi", "macro_indicator", "bls_api", "bls_api", "CPI", ("cpi", "consumer price index", "inflation"), "CUSR0000SA0", "api.bls.gov/publicAPI/v2/timeseries/data/", ("year", "period", "value"), required_env=("BLS_API_KEY",), priority=95),
    SeriesMapping("bls_core_cpi", "macro_indicator", "bls_api", "bls_api", "core CPI", ("core cpi", "core inflation"), "CUSR0000SA0L1E", "api.bls.gov/publicAPI/v2/timeseries/data/", ("year", "period", "value"), required_env=("BLS_API_KEY",), priority=96),
    SeriesMapping("bls_ppi", "macro_indicator", "bls_api", "bls_api", "PPI", ("ppi", "producer price index"), "WPUFD4", "api.bls.gov/publicAPI/v2/timeseries/data/", ("year", "period", "value"), required_env=("BLS_API_KEY",), priority=92),
    SeriesMapping("bls_payrolls", "macro_indicator", "bls_api", "bls_api", "nonfarm payrolls", ("nonfarm payrolls", "non-farm payrolls", "payrolls", "nfp", "jobs report"), "CES0000000001", "api.bls.gov/publicAPI/v2/timeseries/data/", ("year", "period", "value"), required_env=("BLS_API_KEY",), priority=94),
    SeriesMapping("bls_unemployment", "macro_indicator", "bls_api", "bls_api", "unemployment rate", ("unemployment", "jobless rate"), "LNS14000000", "api.bls.gov/publicAPI/v2/timeseries/data/", ("year", "period", "value"), required_env=("BLS_API_KEY",), priority=93),
    SeriesMapping("fred_ppi", "macro_indicator", "fred", "fred", "producer price index", ("ppi", "producer price index", "producer prices"), "PPIACO", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=86),
    SeriesMapping("bea_gdp", "macro_indicator", "bea_api", "bea_api", "GDP/NIPA", ("gdp", "gross domestic product", "real gdp"), "NIPA T10101 line 1", "apps.bea.gov/api/data?method=GetData&DataSetName=NIPA", ("TimePeriod", "LineNumber", "DataValue"), required_env=("BEA_API_KEY",), priority=94),
    SeriesMapping("bea_pce", "macro_indicator", "bea_api", "bea_api", "PCE price index", ("pce", "pce inflation", "pce price", "personal consumption expenditures"), "NIPA T20804 line 1", "apps.bea.gov/api/data?method=GetData&DataSetName=NIPA", ("TimePeriod", "LineNumber", "DataValue"), required_env=("BEA_API_KEY",), priority=93),
    SeriesMapping("fred_core_pce", "macro_indicator", "fred", "fred", "core PCE", ("core pce",), "PCEPILFE", "fred/series/observations", ("date", "value", "realtime_start", "realtime_end"), required_env=("FRED_API_KEY",), priority=88),
    SeriesMapping("imf_weo_growth", "macro_indicator", "imf_data_api", "imf_data_api", "cross-country WEO macro", ("imf", "weo", "gdp growth", "inflation forecast", "current account"), "WEO country.indicator.frequency key", "api.imf.org/external/sdmx/3.0/data/dataflow/...", ("TIME_PERIOD", "value"), priority=70),
    SeriesMapping("world_bank_gdp", "macro_indicator", "world_bank_indicators", "world_bank_indicators", "country GDP/development indicators", ("world bank", "wdi", "country gdp", "development indicator", "external debt"), "NY.GDP.MKTP.CD / indicator id", "api.worldbank.org/v2/country/{country}/indicator/{indicator}", ("date", "country", "value"), priority=68),
    # Rates.
    SeriesMapping("fred_sofr", "rates", "fred", "fred", "SOFR", ("sofr", "secured overnight financing rate"), "SOFR", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=96),
    SeriesMapping("fred_treasury_2y", "rates", "fred", "fred", "2-year Treasury yield", ("2-year treasury", "2 year treasury", "2y treasury", "dgs2"), "DGS2", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=94),
    SeriesMapping("fred_treasury_10y", "rates", "fred", "fred", "10-year Treasury yield", ("10-year treasury", "10 year treasury", "10y treasury", "dgs10", "treasury yield"), "DGS10", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=93),
    SeriesMapping("fred_treasury_30y", "rates", "fred", "fred", "30-year Treasury yield", ("30-year treasury", "30 year treasury", "30y treasury", "dgs30"), "DGS30", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=94),
    SeriesMapping("fred_fed_funds", "rates", "fred", "fred", "effective federal funds rate", ("fed funds", "federal funds", "effective federal funds"), "FEDFUNDS", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=90),
    SeriesMapping("ecb_deposit_facility", "rates", "ecb_data_portal", "ecb_data_portal", "ECB deposit facility rate", ("ecb deposit", "deposit facility", "main refinancing", "euro area rates"), "FM SDMX policy-rate key", "data-api.ecb.europa.eu/service/data/{flow}/{key}", ("TIME_PERIOD", "OBS_VALUE"), priority=82),
    SeriesMapping("boe_bank_rate", "rates", "bank_of_england", "bank_of_england", "Bank of England Bank Rate", ("bank of england", "boe", "bank rate", "sonia"), "IUDBEDR / IUDSOIA", "bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp", ("DATE", "series_code"), priority=82),
    # Commodities.
    SeriesMapping("eia_wti", "commodity", "eia_api", "eia_api", "WTI crude oil spot price", ("wti", "west texas intermediate", "crude oil", "oil price"), "RWTC", "api.eia.gov/v2/petroleum/pri/spt/data/", ("period", "series", "value", "units"), required_env=("EIA_API_KEY",), priority=95),
    SeriesMapping("eia_brent", "commodity", "eia_api", "eia_api", "Brent crude oil spot price", ("brent",), "RBRTE", "api.eia.gov/v2/petroleum/pri/spt/data/", ("period", "series", "value", "units"), required_env=("EIA_API_KEY",), priority=94),
    SeriesMapping("fred_brent", "commodity", "fred", "fred", "Brent crude oil spot price", ("brent",), "DCOILBRENTEU", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=85),
    SeriesMapping("fred_wti", "commodity", "fred", "fred", "WTI crude oil spot price", ("wti", "west texas intermediate", "crude oil", "oil price"), "DCOILWTICO", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=84),
    SeriesMapping("eia_inventory", "commodity", "eia_api", "eia_api", "petroleum inventory", ("crude inventory", "oil inventory", "petroleum inventory", "stockpiles", "stocks"), "WCESTUS1", "api.eia.gov/v2/petroleum/stoc/wstk/data/", ("period", "series", "value", "units"), required_env=("EIA_API_KEY",), priority=88),
    SeriesMapping("eia_natural_gas", "commodity", "eia_api", "eia_api", "Henry Hub natural gas spot price", ("natural gas", "henry hub"), "RNGWHHD", "api.eia.gov/v2/natural-gas/pri/fut/data/", ("period", "series", "value", "units"), required_env=("EIA_API_KEY",), priority=86),
    SeriesMapping("fred_gold", "commodity", "fred", "fred", "gold price", ("gold", "xau"), "GOLDAMGBD228NLBM", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=86),
    SeriesMapping("fred_natural_gas", "commodity", "fred", "fred", "Henry Hub natural gas spot price", ("natural gas", "henry hub"), "DHHNGSP", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=82),
    # Credit and fixed income.
    SeriesMapping("fred_hy_oas", "credit", "fred", "fred", "US high-yield OAS", ("hy oas", "high yield", "high-yield", "high yield spread", "high-yield spread", "junk bond spread"), "BAMLH0A0HYM2", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=93),
    SeriesMapping("fred_ig_oas", "credit", "fred", "fred", "US investment-grade OAS", ("ig oas", "investment grade", "investment-grade", "investment grade spread", "corporate bond spread", "corporate spreads"), "BAMLC0A0CM", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=92),
    SeriesMapping("finra_trace", "fixed_income", "finra_query_api", "finra_query_api", "TRACE fixed-income datasets", ("trace", "corporate bond trade", "fixed income transaction", "bond volume"), "FINRA group/name dataset", "api.finra.org/data/group/{group}/name/{dataset}", ("trade_date", "cusip", "price", "yield", "volume"), required_env=("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET"), priority=90),
    SeriesMapping("bis_debt_securities", "fixed_income", "bis_data_portal", "bis_data_portal", "international debt securities", ("international debt securities", "debt securities", "global bonds"), "WS_DEBT_SEC2_PUB", "stats.bis.org/api/v2/data/dataflow/BIS/{flow}/1.0/{key}", ("TIME_PERIOD", "OBS_VALUE"), priority=75),
    SeriesMapping("bis_lbs_banking", "fixed_income", "bis_data_portal", "bis_data_portal", "BIS locational banking statistics", ("cross-border banking", "international banking", "global liquidity", "banking claims"), "BIS locational banking statistics", "stats.bis.org/api/v2/data/dataflow/BIS/WS_LBS_D_PUB/1.0/{key}", ("TIME_PERIOD", "OBS_VALUE"), priority=76),
    # FX.
    SeriesMapping("fred_eurusd", "fx", "fred", "fred", "EUR/USD", ("eur/usd", "eurusd", "euro dollar", "euro exchange rate"), "DEXUSEU", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=88),
    SeriesMapping("fred_usdjpy", "fx", "fred", "fred", "USD/JPY", ("usd/jpy", "usdjpy", "yen"), "DEXJPUS", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=88),
    SeriesMapping("fred_gbpusd", "fx", "fred", "fred", "GBP/USD", ("gbp/usd", "gbpusd", "sterling", "pound"), "DEXUSUK", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=88),
    SeriesMapping("fred_dollar_index", "fx", "fred", "fred", "broad dollar index", ("dollar", "dollar index", "trade weighted dollar", "broad dollar", "dxy"), "DTWEXBGS", "fred/series/observations", ("date", "value"), required_env=("FRED_API_KEY",), priority=86),
    SeriesMapping("ecb_fx", "fx", "ecb_data_portal", "ecb_data_portal", "ECB EUR FX reference rates", ("ecb fx", "euro reference rate", "eur reference rate"), "EXR SDMX key", "data-api.ecb.europa.eu/service/data/EXR/{key}", ("TIME_PERIOD", "OBS_VALUE"), priority=80),
    SeriesMapping("ecb_hicp", "macro_indicator", "ecb_data_portal", "ecb_data_portal", "Euro area HICP annual rate", ("hicp", "euro area inflation", "eurozone inflation"), "Euro area HICP annual rate", "data-api.ecb.europa.eu/service/data/ICP/{key}", ("TIME_PERIOD", "OBS_VALUE"), priority=81),
    # Derivatives and positioning.
    SeriesMapping("cftc_cot_positioning", "derivatives", "cftc_cot", "cftc_cot", "futures/options positioning", ("cftc", "cot", "commitments of traders", "futures positioning", "open interest", "managed money"), "CFTC PRE 6dca-aqww", "publicreporting.cftc.gov/resource/6dca-aqww", ("report_date", "market", "open_interest", "long", "short"), priority=94),
    SeriesMapping("bis_derivatives", "derivatives", "bis_data_portal", "bis_data_portal", "global derivatives statistics", ("bis derivatives", "otc derivatives", "interest-rate derivatives", "fx derivatives"), "BIS derivatives dataflow", "stats.bis.org/api/v2/data/...", ("TIME_PERIOD", "OBS_VALUE"), priority=70),
)


ASSET_CLASS_ALIASES: dict[str, tuple[str, ...]] = {
    "single_name_equity": ("stock", "share", "company", "issuer", "equity"),
    "equity_index": ("s&p 500", "spx", "nasdaq", "dow", "russell", "equity index", "stock index"),
    "equity_index_future": ("s&p 500 futures", "nasdaq futures", "e-mini", "es futures", "nq futures", "index futures"),
    "fund_etf": ("etf", "spy", "qqq", "hyg", "lqd", "tlt", "gld", "uso"),
    "commodity": ("oil", "wti", "brent", "gold", "natural gas", "gasoline", "copper", "silver"),
    "commodity_future": ("commodity futures", "oil futures", "gold futures"),
    "rates": ("yield", "rate", "sofr", "treasury", "fed funds", "bank rate", "sonia"),
    "credit": ("credit", "spread", "high yield", "investment grade", "oas", "cds"),
    "fixed_income": ("bond", "fixed income", "trace", "corporate bond", "debt securities", "cross-border banking", "international banking", "global liquidity", "banking claims"),
    "fx": ("fx", "forex", "dollar", "yen", "euro", "sterling", "exchange rate", "currency"),
    "derivatives": ("futures", "options", "swap", "derivatives", "open interest", "cot"),
    "macro_indicator": ("inflation", "cpi", "ppi", "payrolls", "jobs", "gdp", "pce", "unemployment", "jolts", "hicp", "global liquidity", "banking claims"),
}


def describe_data_sources() -> list[dict[str, Any]]:
    """Return all data-source descriptions as JSON-compatible dicts."""
    return [description_to_dict(item) for item in DATA_SOURCE_DESCRIPTIONS]


def description_to_dict(description: DataSourceDescription) -> dict[str, Any]:
    payload = asdict(description)
    payload["authority_tier"] = description.authority_tier.value
    payload["license_tag"] = description.license_tag.value
    return payload


def series_mapping_to_dict(mapping: SeriesMapping) -> dict[str, Any]:
    return asdict(mapping)


def data_sources_for_asset_class(asset_class: str, include_planned: bool = False) -> list[dict[str, Any]]:
    """Return source descriptions relevant to one normalized asset class."""
    normalized = normalize_asset_class(asset_class)
    rows = []
    for description in DATA_SOURCE_DESCRIPTIONS:
        if normalized not in description.asset_classes:
            continue
        if not include_planned and description.adapter_status.startswith("planned"):
            continue
        rows.append(description_to_dict(description))
    return rows


def series_mappings_for_claim(claim: str, asset_classes: list[str] | None = None, include_planned: bool = True) -> list[dict[str, Any]]:
    """Return series/dataset mappings whose aliases or asset class match a claim."""
    lower = claim.lower()
    normalized_assets = {normalize_asset_class(item) for item in (asset_classes or []) if item}
    matches: list[SeriesMapping] = []
    for mapping in SERIES_MAPPINGS:
        if not include_planned and mapping.adapter_status.startswith("planned"):
            continue
        alias_match = any(_keyword_in_text(alias, lower) for alias in mapping.aliases)
        asset_match = mapping.asset_class in normalized_assets
        if mapping.source_id == "historical_prices" and not needs_historical_price_data(claim, normalized_assets or {mapping.asset_class}):
            continue
        if alias_match and (not normalized_assets or asset_match):
            matches.append(mapping)
    matches.sort(key=lambda item: item.priority, reverse=True)
    return [series_mapping_to_dict(item) for item in _dedupe_mappings(matches)]


def asset_source_plan(
    claim: str,
    entities: list[dict[str, Any]] | None = None,
    include_planned: bool = True,
) -> dict[str, Any]:
    """Map extracted entities and claim text to data sources and concrete series hints."""
    entity_assets = [
        normalize_asset_class(item.get("asset_class"), item.get("entity_type"))
        for item in (entities or [])
        if item.get("asset_class") or item.get("entity_type")
    ]
    text_assets = _asset_classes_from_text(claim)
    asset_classes = list(dict.fromkeys([*entity_assets, *text_assets]))
    mappings = series_mappings_for_claim(claim, asset_classes, include_planned=include_planned)
    route_ids = [str(item) for item in route_sources(claim, official_only=False, asset_classes=asset_classes).get("routes", [])]
    source_ids = []
    for mapping in mappings:
        source_ids.append(str(mapping["source_id"]))
    source_ids.extend(route_ids)
    source_ids = list(dict.fromkeys(source_ids))
    available_source_ids = []
    for asset_class in asset_classes:
        for source in data_sources_for_asset_class(asset_class, include_planned=include_planned):
            available_source_ids.append(str(source["source_id"]))
    available_source_ids = list(dict.fromkeys(available_source_ids))
    descriptions_by_id = {item.source_id: item for item in DATA_SOURCE_DESCRIPTIONS}
    descriptions = [
        description_to_dict(descriptions_by_id[source_id])
        for source_id in source_ids
        if source_id in descriptions_by_id and (include_planned or not descriptions_by_id[source_id].adapter_status.startswith("planned"))
    ]
    available_descriptions = [
        description_to_dict(descriptions_by_id[source_id])
        for source_id in available_source_ids
        if source_id in descriptions_by_id and (include_planned or not descriptions_by_id[source_id].adapter_status.startswith("planned"))
    ]
    implemented_source_ids = {item["source_id"] for item in descriptions if not str(item["adapter_status"]).startswith("planned")}
    unmapped_assets = [
        asset_class
        for asset_class in asset_classes
        if not any(mapping["asset_class"] == asset_class and mapping["source_id"] in implemented_source_ids for mapping in mappings)
        and not data_sources_for_asset_class(asset_class, include_planned=False)
    ]
    return {
        "claim": claim,
        "asset_classes": asset_classes,
        "source_ids": [item["source_id"] for item in descriptions],
        "available_source_ids": [item["source_id"] for item in available_descriptions],
        "implemented_source_ids": list(implemented_source_ids),
        "series_mappings": mappings,
        "source_descriptions": descriptions,
        "available_source_descriptions": available_descriptions,
        "route_source_ids": route_ids,
        "unmapped_asset_classes": unmapped_assets,
    }


def _asset_classes_from_text(claim: str) -> list[str]:
    lower = claim.lower()
    classes = []
    for asset_class, aliases in ASSET_CLASS_ALIASES.items():
        if any(_keyword_in_text(alias, lower) for alias in aliases):
            classes.append(asset_class)
    return list(dict.fromkeys(classes))


def _keyword_in_text(keyword: str, lower_text: str) -> bool:
    normalized = keyword.lower()
    if re.search(r"\W", normalized):
        return normalized in lower_text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", lower_text) is not None


def _dedupe_mappings(mappings: list[SeriesMapping]) -> list[SeriesMapping]:
    seen = set()
    deduped = []
    for mapping in mappings:
        if mapping.mapping_id in seen:
            continue
        seen.add(mapping.mapping_id)
        deduped.append(mapping)
    return deduped
