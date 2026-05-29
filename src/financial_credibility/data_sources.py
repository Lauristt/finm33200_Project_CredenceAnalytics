"""Structured free/free-tier financial data retrieval.

Provider methods return `SearchResult` objects so the rest of the pipeline can
score all sources through the same extraction and judging path. API keys are
read from `ToolkitConfig`; missing keys simply disable that provider.
"""

from __future__ import annotations

import csv
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from typing import Any

from .claim_intent import is_corporate_transaction_claim
from .config import ToolkitConfig
from .models import ArgumentType, SearchResult
from .net import urlopen_request
from .price_history import (
    PricePoint,
    format_price_history_summary,
    infer_price_window,
    needs_historical_price_data,
    parse_stooq_price_csv,
    summarize_price_history,
)


SEC_CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "sales": ["Revenues", "SalesRevenueNet"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "earnings": ["NetIncomeLoss", "EarningsPerShareDiluted"],
    "net income": ["NetIncomeLoss"],
    "margin": ["GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss", "Revenues"],
    "gross margin": ["GrossProfit", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "operating margin": ["OperatingIncomeLoss", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "net margin": ["NetIncomeLoss", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "cash flow": ["NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"],
    "free cash flow": ["NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "capital expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "assets": ["Assets", "AssetsCurrent"],
    "liabilities": ["Liabilities", "LiabilitiesCurrent"],
    "current ratio": ["AssetsCurrent", "LiabilitiesCurrent"],
    "working capital": ["AssetsCurrent", "LiabilitiesCurrent"],
    "debt": ["LongTermDebt", "LongTermDebtCurrent", "ShortTermBorrowings", "ShortTermDebt"],
    "net debt": [
        "LongTermDebt",
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
        "ShortTermDebt",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
}

MARKET_PRICE_SYMBOLS = {
    "SPX": {
        "label": "S&P 500 Index",
        "stooq": ["^spx"],
        "alpha_vantage": ["SPY"],
        "fmp": ["^GSPC", "SPY"],
        "finnhub": ["^GSPC", "SPY"],
        "marketstack": ["^GSPC", "SPY"],
        "tiingo": ["spy"],
    },
    "NDQ": {
        "label": "Nasdaq Composite Index",
        "stooq": ["^ndq"],
        "alpha_vantage": ["QQQ"],
        "fmp": ["^IXIC", "QQQ"],
        "finnhub": ["^IXIC", "QQQ"],
        "marketstack": ["^IXIC", "QQQ"],
        "tiingo": ["qqq"],
    },
    "NDX": {
        "label": "Nasdaq 100 Index",
        "stooq": ["^ndx"],
        "alpha_vantage": ["QQQ"],
        "fmp": ["^NDX", "QQQ"],
        "finnhub": ["^NDX", "QQQ"],
        "marketstack": ["^NDX", "QQQ"],
        "tiingo": ["qqq"],
    },
    "DJIA": {
        "label": "Dow Jones Industrial Average",
        "stooq": ["^dji"],
        "alpha_vantage": ["DIA"],
        "fmp": ["^DJI", "DIA"],
        "finnhub": ["^DJI", "DIA"],
        "marketstack": ["^DJI", "DIA"],
        "tiingo": ["dia"],
    },
    "RUT": {
        "label": "Russell 2000 Index",
        "stooq": ["iwm.us", "^rut"],
        "alpha_vantage": ["IWM"],
        "fmp": ["^RUT", "IWM"],
        "finnhub": ["^RUT", "IWM"],
        "marketstack": ["^RUT", "IWM"],
        "tiingo": ["iwm"],
    },
    "VIX": {
        "label": "CBOE Volatility Index",
        "stooq": ["^vix"],
        "fmp": ["^VIX"],
        "finnhub": ["^VIX"],
        "marketstack": ["^VIX"],
    },
}

FRED_INDEX_PRICE_SERIES = {
    "SPX": ("SP500", "S&P 500 Index"),
    "NDQ": ("NASDAQCOM", "Nasdaq Composite Index"),
    "DJIA": ("DJIA", "Dow Jones Industrial Average"),
}

FRED_SERIES = {
    "core pce": "PCEPILFE",
    "pce price": "PCEPI",
    "pce inflation": "PCEPI",
    "pce": "PCEPI",
    "sofr": "SOFR",
    "secured overnight financing rate": "SOFR",
    "2 year treasury": "DGS2",
    "2-year treasury": "DGS2",
    "2y treasury": "DGS2",
    "dgs2": "DGS2",
    "10 year treasury": "DGS10",
    "10-year treasury": "DGS10",
    "10y treasury": "DGS10",
    "dgs10": "DGS10",
    "30 year treasury": "DGS30",
    "30-year treasury": "DGS30",
    "30y treasury": "DGS30",
    "dgs30": "DGS30",
    "treasury yield": "DGS10",
    "treasury": "DGS10",
    "fed funds": "FEDFUNDS",
    "federal funds": "FEDFUNDS",
    "effective federal funds": "FEDFUNDS",
    "nonfarm payrolls": "PAYEMS",
    "non-farm payrolls": "PAYEMS",
    "nfp": "PAYEMS",
    "payrolls": "PAYEMS",
    "job openings": "JTSJOL",
    "jolts": "JTSJOL",
    "hourly earnings": "CES0500000003",
    "wage": "CES0500000003",
    "ppi": "PPIACO",
    "producer price index": "PPIACO",
    "high yield spread": "BAMLH0A0HYM2",
    "hy oas": "BAMLH0A0HYM2",
    "high-yield oas": "BAMLH0A0HYM2",
    "investment grade spread": "BAMLC0A0CM",
    "ig oas": "BAMLC0A0CM",
    "corporate oas": "BAMLC0A0CM",
    "brent": "DCOILBRENTEU",
    "wti": "DCOILWTICO",
    "crude oil": "DCOILWTICO",
    "oil price": "DCOILWTICO",
    "gold": "GOLDAMGBD228NLBM",
    "natural gas": "DHHNGSP",
    "henry hub": "DHHNGSP",
    "eur/usd": "DEXUSEU",
    "euro dollar": "DEXUSEU",
    "euro exchange rate": "DEXUSEU",
    "usd/jpy": "DEXJPUS",
    "yen": "DEXJPUS",
    "gbp/usd": "DEXUSUK",
    "sterling": "DEXUSUK",
    "pound": "DEXUSUK",
    "usd/cad": "DEXCAUS",
    "canadian dollar": "DEXCAUS",
    "usd/chf": "DEXCHUS",
    "swiss franc": "DEXCHUS",
    "aud/usd": "DEXUSAL",
    "australian dollar": "DEXUSAL",
    "dollar index": "DTWEXBGS",
    "trade weighted dollar": "DTWEXBGS",
    "broad dollar": "DTWEXBGS",
    "cpi": "CPIAUCSL",
    "inflation": "CPIAUCSL",
    "interest": "FEDFUNDS",
    "rate": "FEDFUNDS",
    "gdp": "GDP",
    "unemployment": "UNRATE",
    "yield": "DGS10",
}

BLS_SERIES = {
    "core cpi": ("CUSR0000SA0L1E", "BLS core CPI for all urban consumers"),
    "cpi": ("CUSR0000SA0", "BLS CPI for all urban consumers"),
    "consumer price index": ("CUSR0000SA0", "BLS CPI for all urban consumers"),
    "ppi": ("WPUFD4", "BLS Producer Price Index: final demand"),
    "producer price index": ("WPUFD4", "BLS Producer Price Index: final demand"),
    "nonfarm payrolls": ("CES0000000001", "BLS all employees, total nonfarm"),
    "non-farm payrolls": ("CES0000000001", "BLS all employees, total nonfarm"),
    "payrolls": ("CES0000000001", "BLS all employees, total nonfarm"),
    "nfp": ("CES0000000001", "BLS all employees, total nonfarm"),
    "unemployment": ("LNS14000000", "BLS unemployment rate"),
    "job openings": ("JTSJOL", "BLS JOLTS job openings"),
    "jolts": ("JTSJOL", "BLS JOLTS job openings"),
    "hourly earnings": ("CES0500000003", "BLS average hourly earnings, private employees"),
    "wage": ("CES0500000003", "BLS average hourly earnings, private employees"),
}

BEA_SERIES = {
    "core pce": ("NIPA", "T20804", "25", "M", "BEA core PCE price index"),
    "real gdp": ("NIPA", "T10101", "1", "Q", "BEA NIPA real GDP percent change"),
    "gdp": ("NIPA", "T10101", "1", "Q", "BEA NIPA real GDP percent change"),
    "gross domestic product": ("NIPA", "T10101", "1", "Q", "BEA NIPA real GDP percent change"),
    "pce price": ("NIPA", "T20804", "1", "M", "BEA PCE price index"),
    "pce inflation": ("NIPA", "T20804", "1", "M", "BEA PCE price index"),
    "pce": ("NIPA", "T20804", "1", "M", "BEA PCE price index"),
    "personal income": ("NIPA", "T20600", "1", "M", "BEA personal income"),
    "nipa": ("NIPA", "T10101", "1", "Q", "BEA NIPA table data"),
}

EIA_SERIES = {
    "brent": ("petroleum/pri/spt", "RBRTE", "EIA Brent crude oil spot price"),
    "wti": ("petroleum/pri/spt", "RWTC", "EIA WTI crude oil spot price"),
    "crude oil": ("petroleum/pri/spt", "RWTC", "EIA WTI crude oil spot price"),
    "oil price": ("petroleum/pri/spt", "RWTC", "EIA WTI crude oil spot price"),
    "oil inventory": ("petroleum/stoc/wstk", "WCESTUS1", "EIA U.S. crude oil ending stocks excluding SPR"),
    "crude inventory": ("petroleum/stoc/wstk", "WCESTUS1", "EIA U.S. crude oil ending stocks excluding SPR"),
    "petroleum inventory": ("petroleum/stoc/wstk", "WCESTUS1", "EIA U.S. crude oil ending stocks excluding SPR"),
    "stockpiles": ("petroleum/stoc/wstk", "WCESTUS1", "EIA U.S. crude oil ending stocks excluding SPR"),
    "natural gas": ("natural-gas/pri/fut", "RNGWHHD", "EIA Henry Hub natural gas spot price"),
    "henry hub": ("natural-gas/pri/fut", "RNGWHHD", "EIA Henry Hub natural gas spot price"),
    "gasoline": ("petroleum/pri/gnd", "EMM_EPMR_PTE_NUS_DPG", "EIA U.S. regular gasoline retail price"),
}

CFTC_COT_DATASET = "6dca-aqww"

CFTC_MARKETS = {
    "wti": "CRUDE OIL",
    "crude": "CRUDE OIL",
    "oil": "CRUDE OIL",
    "brent": "BRENT",
    "gold": "GOLD",
    "silver": "SILVER",
    "copper": "COPPER",
    "natural gas": "NATURAL GAS",
    "corn": "CORN",
    "wheat": "WHEAT",
    "soybean": "SOYBEANS",
    "s&p": "S&P",
    "spx": "S&P",
    "nasdaq": "NASDAQ",
    "treasury": "TREASURY",
}

ECB_SERIES = {
    "eur/usd": ("EXR", "D.USD.EUR.SP00.A", "ECB euro foreign exchange reference rate: USD per EUR"),
    "euro dollar": ("EXR", "D.USD.EUR.SP00.A", "ECB euro foreign exchange reference rate: USD per EUR"),
    "exchange rate": ("EXR", "D.USD.EUR.SP00.A", "ECB euro foreign exchange reference rate"),
    "deposit facility": ("FM", "B.U2.EUR.4F.KR.DFR.LEV", "ECB deposit facility rate"),
    "main refinancing": ("FM", "B.U2.EUR.4F.KR.MRR_FR.LEV", "ECB main refinancing operations rate"),
    "hicp": ("ICP", "M.U2.N.000000.4.ANR", "Euro area HICP annual rate"),
    "euro area inflation": ("ICP", "M.U2.N.000000.4.ANR", "Euro area HICP annual rate"),
}

BIS_SERIES = {
    "cross-border": ("WS_LBS_D_PUB", "Q.S.C.A.TO1.A.5J.A.US.A.5J.N", "BIS locational banking statistics"),
    "international banking": ("WS_LBS_D_PUB", "Q.S.C.A.TO1.A.5J.A.US.A.5J.N", "BIS international banking statistics"),
    "debt securities": ("WS_DEBT_SEC2_PUB", "Q.US.3P.G.1.C.A.D.TO1.A.U.A.A.A.I", "BIS debt securities statistics"),
}

IMF_COUNTRIES = {
    "united states": "USA",
    "u.s.": "USA",
    "us": "USA",
    "usa": "USA",
    "china": "CHN",
    "cn": "CHN",
    "japan": "JPN",
    "united kingdom": "GBR",
    "uk": "GBR",
    "germany": "DEU",
    "france": "FRA",
    "india": "IND",
    "brazil": "BRA",
    "canada": "CAN",
    "mexico": "MEX",
}

IMF_WEO_INDICATORS = {
    "real gdp growth": ("NGDP_RPCH", "IMF WEO real GDP growth"),
    "gdp growth": ("NGDP_RPCH", "IMF WEO real GDP growth"),
    "gross domestic product growth": ("NGDP_RPCH", "IMF WEO real GDP growth"),
    "inflation": ("PCPIPCH", "IMF WEO inflation"),
    "cpi": ("PCPIPCH", "IMF WEO inflation"),
    "current account": ("BCA_NGDPD", "IMF WEO current account balance as percent of GDP"),
    "unemployment": ("LUR", "IMF WEO unemployment rate"),
}

WORLD_BANK_INDICATORS = {
    "gross domestic product": "NY.GDP.MKTP.CD",
    "gdp": "NY.GDP.MKTP.CD",
    "total population": "SP.POP.TOTL",
    "population": "SP.POP.TOTL",
    "cpi": "FP.CPI.TOTL.ZG",
    "inflation": "FP.CPI.TOTL.ZG",
    "unemployment": "SL.UEM.TOTL.ZS",
    "external debt": "DT.DOD.DECT.CD",
    "international debt": "DT.DOD.DECT.CD",
    "current account": "BN.CAB.XOKA.CD",
    "poverty": "SI.POV.DDAY",
}

WORLD_BANK_COUNTRIES = {
    "all countries": "all",
    "all country": "all",
    "united states": "US",
    "u.s.": "US",
    "us": "US",
    "usa": "USA",
    "china": "CN",
    "cn": "CN",
    "chn": "CHN",
    "euro area": "EMU",
    "eurozone": "EMU",
    "japan": "JP",
    "united kingdom": "GB",
    "uk": "GB",
    "germany": "DE",
    "france": "FR",
    "india": "IN",
    "brazil": "BR",
    "global": "WLD",
    "world": "WLD",
}

BOE_SERIES = {
    "bank rate": ("IUDBEDR", "Bank of England Bank Rate"),
    "base rate": ("IUDBEDR", "Bank of England Bank Rate"),
    "sonia": ("IUDSOIA", "Bank of England SONIA interest rate"),
    "sterling": ("XUDLBK67", "Bank of England sterling effective exchange rate index"),
}

FINRA_DATASETS = {
    "treasury": ("fixedIncomeMarket", "treasuryDailyAggregates", "FINRA Treasury Daily Aggregates"),
    "ust": ("fixedIncomeMarket", "treasuryDailyAggregates", "FINRA Treasury Daily Aggregates"),
    "agency": ("fixedIncomeMarket", "agencyMarketBreadth", "FINRA Agency Debt Market Breadth"),
    "144a": ("fixedIncomeMarket", "corporate144AMarketBreadth", "FINRA Corporate 144A Debt Market Breadth"),
    "sentiment": ("fixedIncomeMarket", "corporateMarketSentiment", "FINRA Corporate Debt Market Sentiment"),
    "volume": ("fixedIncomeMarket", "corporateMarketSentiment", "FINRA Corporate Debt Market Sentiment"),
    "corporate bond": ("fixedIncomeMarket", "corporateMarketBreadth", "FINRA Corporate Debt Market Breadth"),
    "corporate debt": ("fixedIncomeMarket", "corporateMarketBreadth", "FINRA Corporate Debt Market Breadth"),
    "fixed income": ("fixedIncomeMarket", "corporateMarketBreadth", "FINRA Corporate Debt Market Breadth"),
    "trace": ("fixedIncomeMarket", "corporateMarketBreadth", "FINRA Corporate Debt Market Breadth"),
    "finra": ("fixedIncomeMarket", "corporateMarketBreadth", "FINRA Corporate Debt Market Breadth"),
}


@dataclass
class FreeDataSourceClient:
    """Client for structured data sources that are useful for US equity claims."""

    config: ToolkitConfig

    def query(
        self,
        claim: str,
        ticker: str,
        argument_type: ArgumentType,
        max_results: int = 8,
        as_of_date: str | None = None,
        allowed_sources: list[str] | set[str] | None = None,
    ) -> tuple[list[SearchResult], list[str]]:
        """Query configured providers and return deduplicated search results."""
        results: list[SearchResult] = []
        notes: list[str] = []
        allowed = set(allowed_sources or [])

        providers = [
            ("historical_prices", lambda: self.historical_prices(ticker, claim, as_of_date)),
            ("sec_company_facts", lambda: self.sec_company_facts(claim, ticker, as_of_date=as_of_date)),
            ("sec_recent_filings", lambda: self.sec_recent_filings(ticker, as_of_date=as_of_date)),
            ("alpha_vantage", lambda: self.alpha_vantage(ticker)),
            ("finnhub", lambda: self.finnhub(ticker)),
            ("fmp", lambda: self.fmp(ticker)),
            ("bls_api", lambda: self.bls_api(claim, as_of_date=as_of_date)),
            ("bea_api", lambda: self.bea_api(claim, as_of_date=as_of_date)),
            ("eia_api", lambda: self.eia_api(claim, as_of_date=as_of_date)),
            ("fred", lambda: self.fred(claim, as_of_date=as_of_date)),
            ("treasury_fiscal_data", lambda: self.treasury_fiscal_data(claim, as_of_date=as_of_date)),
            ("gleif_entity", lambda: self.gleif_entity(claim, ticker)),
            ("cftc_cot", lambda: self.cftc_cot(claim, as_of_date=as_of_date)),
            ("ecb_data_portal", lambda: self.ecb_data_portal(claim)),
            ("bis_data_portal", lambda: self.bis_data_portal(claim)),
            ("imf_data_api", lambda: self.imf_data_api(claim)),
            ("world_bank_indicators", lambda: self.world_bank_indicators(claim)),
            ("bank_of_england", lambda: self.bank_of_england(claim, date_to=as_of_date)),
            ("finra_query_api", lambda: self.finra_query_api(claim, as_of_date=as_of_date)),
            ("openfigi", lambda: self.openfigi(claim, ticker)),
            ("marketstack", lambda: self.marketstack(ticker)),
            ("tiingo", lambda: self.tiingo(ticker)),
            ("stooq", lambda: self.stooq(ticker, as_of_date=as_of_date)),
        ]
        if self.config.enable_yahoo_fallback:
            providers.append(("yahoo_chart_unofficial", lambda: self.yahoo_chart(ticker)))

        for name, provider in providers:
            if len(results) >= max_results:
                break
            if allowed and not _provider_allowed(name, allowed):
                continue
            claim_needs_history = needs_historical_price_data(claim)
            if name == "historical_prices" and not claim_needs_history:
                continue
            if name in {"marketstack", "tiingo", "stooq", "yahoo_chart_unofficial"} and claim_needs_history:
                continue
            try:
                provider_results = provider()
                results.extend(provider_results)
                if provider_results:
                    notes.append(f"{name}: {len(provider_results)} result(s)")
                elif name == "historical_prices":
                    provider_notes = "; ".join(
                        item
                        for item in getattr(self, "_last_historical_price_errors", [])
                        if item
                    )
                    suffix = f" ({provider_notes})" if provider_notes else ""
                    notes.append(
                        "historical_prices: no historical price series returned; configure ALPHA_VANTAGE_API_KEY, "
                        "FMP_API_KEY, or FINNHUB_API_KEY, or use a Stooq plan that allows historical CSV downloads"
                        f"{suffix}"
                    )
            except Exception as exc:
                notes.append(f"{name} failed: {exc}")

        return _dedupe(results)[:max_results], notes

    def sec_company_facts(self, claim: str, ticker: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return recent SEC XBRL facts for concepts implied by the claim."""
        concept_names = self._concepts_for_claim(claim)
        if not concept_names:
            return []
        cik = self._ticker_to_cik(ticker)
        if cik is None:
            return []
        data = self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", sec=True)
        from datetime import date

        as_of = _parse_iso_date(as_of_date)
        facts_by_taxonomy = data.get("facts", {})
        snippets = []
        latest_date = None

        for concept, concept_data in self._matching_sec_concepts(facts_by_taxonomy, concept_names, claim):
            if not concept_data:
                continue
            units = concept_data.get("units", {})
            for unit_name, values in units.items():
                # Surface full-year AND single-quarter figures, de-duplicated by reporting
                # period (end date + period kind), so the value for the period a claim refers
                # to is present. Previously only the 2 most-recently-FILED values were kept,
                # which let recent quarters crowd out the relevant fiscal-year value.
                by_period: dict[tuple, dict] = {}
                for value in values:
                    end = value.get("end")
                    if value.get("val") is None or not value.get("filed") or not end:
                        continue
                    filed = _parse_iso_date(value.get("filed"))
                    if as_of and filed and filed > as_of:
                        continue
                    start = value.get("start")
                    if start:
                        try:
                            span = (date.fromisoformat(end) - date.fromisoformat(start)).days
                        except ValueError:
                            continue
                        if 350 <= span <= 380:
                            kind = "fiscal year"
                        elif 80 <= span <= 100:
                            kind = "fiscal quarter"
                        else:
                            continue  # skip overlapping half-year / nine-month periods
                    elif value.get("form") == "10-K":
                        kind = "fiscal year"
                    else:
                        continue
                    key = (end, kind)
                    prev = by_period.get(key)
                    if prev is None or value.get("filed", "") > prev.get("filed", ""):
                        by_period[key] = value
                for (end, kind), value in sorted(by_period.items(), key=lambda kv: kv[0][0], reverse=True)[:8]:
                    latest_date = max(latest_date or "", value.get("filed", "")) or latest_date
                    snippets.append(
                        f"{concept} ({unit_name}) for {kind} ending {end}: "
                        f"{value.get('val')} (form {value.get('form')})"
                    )

        if not snippets:
            return []

        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        return [
            SearchResult(
                title=f"SEC Company Facts for {ticker.upper()}",
                url=url,
                snippet="; ".join(snippets[:30]),
                published_at=latest_date,
                source="SEC EDGAR",
                raw={"provider": "sec_company_facts", "cik": cik},
            )
        ]

    def sec_recent_filings(self, ticker: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return recent SEC 10-K, 10-Q, and 8-K filings for the ticker."""
        cik = self._ticker_to_cik(ticker)
        if cik is None:
            return []
        data = self._get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", sec=True)
        as_of = _parse_iso_date(as_of_date)
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        results = []
        for idx, form in enumerate(forms[:20]):
            if form not in {"10-K", "10-Q", "8-K"}:
                continue
            accession = accession_numbers[idx].replace("-", "") if idx < len(accession_numbers) else ""
            primary_doc = primary_docs[idx] if idx < len(primary_docs) else ""
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"
                if accession and primary_doc
                else f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
            )
            filing_date = dates[idx] if idx < len(dates) else None
            parsed_filing_date = _parse_iso_date(filing_date)
            if as_of and parsed_filing_date and parsed_filing_date > as_of:
                continue
            results.append(
                SearchResult(
                    title=f"SEC {form} filing for {ticker.upper()}",
                    url=url,
                    snippet=f"{ticker.upper()} filed form {form} on {filing_date}.",
                    published_at=filing_date,
                    source="SEC EDGAR",
                    raw={"provider": "sec_recent_filings", "form": form, "cik": cik},
                )
            )
            if len(results) >= 3:
                break
        return results

    def alpha_vantage(self, ticker: str) -> list[SearchResult]:
        """Return Alpha Vantage overview and annual earnings snippets."""
        key = self.config.alpha_vantage_api_key
        if not key:
            return []
        results = []
        overview = self._get_json(
            "https://www.alphavantage.co/query?"
            + urllib.parse.urlencode({"function": "OVERVIEW", "symbol": ticker, "apikey": key})
        )
        if overview and not overview.get("Note") and not overview.get("Information"):
            fields = ["Name", "MarketCapitalization", "PERatio", "EPS", "RevenueTTM", "ProfitMargin"]
            snippet = "; ".join(f"{field}: {overview.get(field)}" for field in fields if overview.get(field))
            results.append(
                SearchResult(
                    title=f"Alpha Vantage company overview for {ticker.upper()}",
                    url=f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker.upper()}",
                    snippet=snippet,
                    source="Alpha Vantage",
                    raw={"provider": "alpha_vantage_overview"},
                )
            )
        earnings = self._get_json(
            "https://www.alphavantage.co/query?"
            + urllib.parse.urlencode({"function": "EARNINGS", "symbol": ticker, "apikey": key})
        )
        annual = earnings.get("annualEarnings", []) if isinstance(earnings, dict) else []
        if annual:
            latest = annual[0]
            results.append(
                SearchResult(
                    title=f"Alpha Vantage earnings for {ticker.upper()}",
                    url=f"https://www.alphavantage.co/query?function=EARNINGS&symbol={ticker.upper()}",
                    snippet=f"Latest annual EPS: {latest.get('reportedEPS')} fiscalDateEnding {latest.get('fiscalDateEnding')}",
                    published_at=latest.get("reportedDate") or latest.get("fiscalDateEnding"),
                    source="Alpha Vantage",
                    raw={"provider": "alpha_vantage_earnings"},
                )
            )
        return results

    def finnhub(self, ticker: str) -> list[SearchResult]:
        """Return Finnhub profile and basic financial metric snippets."""
        key = self.config.finnhub_api_key
        if not key:
            return []
        results = []
        profile = self._get_json(
            "https://finnhub.io/api/v1/stock/profile2?"
            + urllib.parse.urlencode({"symbol": ticker, "token": key})
        )
        if profile and profile.get("name"):
            results.append(
                SearchResult(
                    title=f"Finnhub profile for {ticker.upper()}",
                    url=f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker.upper()}",
                    snippet=f"{profile.get('name')} market cap {profile.get('marketCapitalization')} exchange {profile.get('exchange')}",
                    source="Finnhub",
                    raw={"provider": "finnhub_profile"},
                )
            )
        metrics = self._get_json(
            "https://finnhub.io/api/v1/stock/metric?"
            + urllib.parse.urlencode({"symbol": ticker, "metric": "all", "token": key})
        )
        metric = metrics.get("metric", {}) if isinstance(metrics, dict) else {}
        if metric:
            fields = ["peNormalizedAnnual", "epsGrowth5Y", "revenueGrowth5Y", "grossMarginAnnual", "netMarginAnnual"]
            snippet = "; ".join(f"{field}: {metric.get(field)}" for field in fields if metric.get(field) is not None)
            if snippet:
                results.append(
                    SearchResult(
                        title=f"Finnhub basic financial metrics for {ticker.upper()}",
                        url=f"https://finnhub.io/api/v1/stock/metric?symbol={ticker.upper()}",
                        snippet=snippet,
                        source="Finnhub",
                        raw={"provider": "finnhub_metric"},
                    )
                )
        return results

    def fmp(self, ticker: str) -> list[SearchResult]:
        """Return FMP profile and income statement snippets."""
        key = self.config.fmp_api_key
        if not key:
            return []
        results = []
        profile = self._get_json(
            "https://financialmodelingprep.com/stable/profile?"
            + urllib.parse.urlencode({"symbol": ticker.upper(), "apikey": key})
        )
        if isinstance(profile, list) and profile:
            item = profile[0]
            results.append(
                SearchResult(
                    title=f"FMP profile for {ticker.upper()}",
                    url=f"https://financialmodelingprep.com/stable/profile?symbol={ticker.upper()}",
                    snippet=f"{item.get('companyName')} price {item.get('price')} market cap {item.get('mktCap')} sector {item.get('sector')}",
                    source="Financial Modeling Prep",
                    raw={"provider": "fmp_profile"},
                )
            )
        income = self._get_json(
            "https://financialmodelingprep.com/stable/income-statement?"
            + urllib.parse.urlencode({"symbol": ticker.upper(), "limit": 2, "apikey": key})
        )
        if isinstance(income, list) and income:
            item = income[0]
            results.append(
                SearchResult(
                    title=f"FMP income statement for {ticker.upper()}",
                    url=f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker.upper()}",
                    snippet=(
                        f"date {item.get('date')} revenue {item.get('revenue')} netIncome {item.get('netIncome')} "
                        f"eps {item.get('eps')}"
                    ),
                    published_at=item.get("fillingDate") or item.get("date"),
                    source="Financial Modeling Prep",
                    raw={"provider": "fmp_income_statement"},
                )
            )
        return results

    def fred(self, claim: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return a FRED macro series when the claim contains a known keyword."""
        key = self.config.fred_api_key
        if not key:
            return []
        series_id = self._fred_series_for_claim(claim)
        if not series_id:
            return []
        params = {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 3,
        }
        if _parse_iso_date(as_of_date):
            params["observation_end"] = str(as_of_date)[:10]
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)
        data = self._get_json(url)
        observations = data.get("observations", []) if isinstance(data, dict) else []
        if not observations:
            return []
        snippet = "; ".join(f"{obs.get('date')}: {obs.get('value')}" for obs in observations)
        return [
            SearchResult(
                title=f"FRED macro series {series_id}",
                url=f"https://fred.stlouisfed.org/series/{series_id}",
                snippet=snippet,
                published_at=observations[0].get("date"),
                source="FRED",
                raw={"provider": "fred", "series_id": series_id, "observations": observations},
            )
        ]

    def bls_api(self, claim: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return BLS public data API observations for labor and price-stat claims."""
        series = _series_for_claim(claim, BLS_SERIES)
        if not series:
            return []
        series_id, label = series
        start_year, end_year = _year_window_for_claim(claim, as_of_date, default_years=3)
        body: dict[str, Any] = {
            "seriesid": [series_id],
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if self.config.bls_api_key:
            body["registrationkey"] = self.config.bls_api_key
        url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
        payload = self._post_json(url, body)
        series_blocks = ((payload.get("Results") or {}).get("series") or []) if isinstance(payload, dict) else []
        rows = []
        if series_blocks and isinstance(series_blocks[0], dict):
            for row in series_blocks[0].get("data") or []:
                if not isinstance(row, dict) or row.get("value") in {None, ""}:
                    continue
                rows.append(
                    {
                        "date": _bls_period_label(row),
                        "value": str(row.get("value")),
                        "year": row.get("year"),
                        "period": row.get("period"),
                        "raw": row,
                    }
                )
        if not rows:
            return []
        return [
            SearchResult(
                title=f"{label} ({series_id})",
                url="https://www.bls.gov/developers/",
                snippet=_observation_snippet(rows),
                published_at=rows[0].get("date"),
                source="BLS Public Data API",
                raw={"provider": "bls_api", "series_id": series_id, "rows": rows},
            )
        ]

    def bea_api(self, claim: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return BEA API observations for mapped national-account claims."""
        key = self.config.bea_api_key
        if not key:
            return []
        series = _series_for_claim(claim, BEA_SERIES)
        if not series:
            return []
        dataset, table_name, line_number, frequency, label = series
        _, end_year = _year_window_for_claim(claim, as_of_date, default_years=3)
        params = {
            "UserID": key,
            "method": "GetData",
            "DataSetName": dataset,
            "TableName": table_name,
            "Frequency": frequency,
            "Year": "X" if not end_year else str(end_year),
            "ResultFormat": "JSON",
        }
        url = "https://apps.bea.gov/api/data?" + urllib.parse.urlencode(params)
        payload = self._get_json(url)
        rows = _bea_data_rows(payload)
        if line_number:
            line_rows = [row for row in rows if str(row.get("LineNumber")) == str(line_number)]
            rows = line_rows or rows
        usable = []
        for row in rows[:8]:
            value = row.get("DataValue")
            if value in {None, ""}:
                continue
            usable.append(
                {
                    "date": str(row.get("TimePeriod") or row.get("Year") or ""),
                    "value": str(value),
                    "line_number": row.get("LineNumber"),
                    "line_description": row.get("LineDescription"),
                    "raw": row,
                }
            )
        if not usable:
            return []
        return [
            SearchResult(
                title=f"{label} ({table_name})",
                url=url,
                snippet=_observation_snippet(usable),
                published_at=usable[0].get("date"),
                source="BEA API",
                raw={
                    "provider": "bea_api",
                    "dataset": dataset,
                    "table_name": table_name,
                    "line_number": line_number,
                    "frequency": frequency,
                    "rows": usable,
                },
            )
        ]

    def eia_api(self, claim: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return EIA APIv2 observations for mapped energy commodity claims."""
        key = self.config.eia_api_key
        if not key:
            return []
        series = _series_for_claim(claim, EIA_SERIES)
        if not series:
            return []
        route, series_id, label = series
        params = {
            "api_key": key,
            "frequency": "daily",
            "data[0]": "value",
            "facets[series][]": series_id,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": 5,
        }
        if _parse_iso_date(as_of_date):
            params["end"] = str(as_of_date)[:10]
        url = _join_url("https://api.eia.gov/v2", *route.split("/"), "data") + "/?" + urllib.parse.urlencode(params)
        payload = self._get_json(url)
        data = ((payload.get("response") or {}).get("data") or []) if isinstance(payload, dict) else []
        rows = []
        for row in data[:5]:
            if not isinstance(row, dict) or row.get("value") in {None, ""}:
                continue
            rows.append(
                {
                    "date": str(row.get("period") or ""),
                    "value": str(row.get("value")),
                    "series": row.get("series"),
                    "unit": row.get("units"),
                    "raw": row,
                }
            )
        if not rows:
            return []
        return [
            SearchResult(
                title=f"{label} ({series_id})",
                url=url,
                snippet=_observation_snippet(rows),
                published_at=rows[0].get("date"),
                source="EIA Open Data API",
                raw={"provider": "eia_api", "route": route, "series_id": series_id, "rows": rows},
            )
        ]

    def treasury_fiscal_data(self, claim: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return U.S. Treasury fiscal data for federal debt/fiscal claims."""
        if not _needs_treasury_data(claim):
            return []
        params = {"sort": "-record_date", "page[size]": 3}
        if _parse_iso_date(as_of_date):
            params["filter"] = f"record_date:lte:{str(as_of_date)[:10]}"
        url = (
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
            "v2/accounting/od/debt_to_penny?"
            + urllib.parse.urlencode(params)
        )
        data = self._get_json(url)
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            return []
        snippet = "; ".join(
            f"{row.get('record_date')}: debt_held_public {row.get('debt_held_public_amt')} intragov {row.get('intragov_hold_amt')}"
            for row in rows
        )
        return [
            SearchResult(
                title="U.S. Treasury Debt to the Penny",
                url="https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny",
                snippet=snippet,
                published_at=rows[0].get("record_date"),
                source="U.S. Treasury Fiscal Data",
                raw={"provider": "treasury_fiscal_data", "dataset": "debt_to_penny", "rows": rows},
            )
        ]

    def gleif_entity(self, claim: str, ticker: str) -> list[SearchResult]:
        """Return a lightweight GLEIF entity lookup when entity mapping is requested."""
        if not _needs_gleif_data(claim):
            return []
        url = "https://api.gleif.org/api/v1/lei-records?" + urllib.parse.urlencode(
            {"filter[entity.names]": ticker.upper(), "page[size]": 3}
        )
        data = self._get_json(url)
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            return []
        snippets = []
        for row in rows:
            attributes = row.get("attributes", {}) if isinstance(row, dict) else {}
            entity = attributes.get("entity", {}) if isinstance(attributes, dict) else {}
            legal_name = entity.get("legalName", {}).get("name") if isinstance(entity, dict) else None
            snippets.append(f"LEI {row.get('id')} legalName {legal_name}")
        return [
            SearchResult(
                title=f"GLEIF LEI records for {ticker.upper()}",
                url=url,
                snippet="; ".join(snippets),
                source="GLEIF",
                raw={"provider": "gleif_entity", "rows": rows, "lei": rows[0].get("id")},
            )
        ]

    def cftc_cot(self, claim: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return CFTC COT public reporting rows for futures-positioning claims."""
        if not _needs_cftc_data(claim):
            return []
        market = _first_mapping_match(claim, CFTC_MARKETS)
        params = {
            "$limit": 5,
            "$order": "report_date_as_yyyy_mm_dd DESC",
        }
        where_clauses = []
        if market:
            where_clauses.append(f"upper(market_and_exchange_names) like '%{market.upper()}%'")
        if _parse_iso_date(as_of_date):
            where_clauses.append(f"report_date_as_yyyy_mm_dd <= '{str(as_of_date)[:10]}'")
        if where_clauses:
            params["$where"] = " and ".join(where_clauses)
        if self.config.cftc_app_token:
            params["$$app_token"] = self.config.cftc_app_token
        url = _join_url(self.config.cftc_base_url, CFTC_COT_DATASET) + "?" + urllib.parse.urlencode(params)
        rows = self._get_json(url)
        if not isinstance(rows, list) or not rows:
            return []
        snippets = []
        for row in rows[:5]:
            snippets.append(
                " ".join(
                    part
                    for part in [
                        f"{row.get('report_date_as_yyyy_mm_dd')}:",
                        str(row.get("market_and_exchange_names") or row.get("market_and_exchange_name") or "").strip(),
                        f"open_interest {row.get('open_interest_all')}" if row.get("open_interest_all") is not None else "",
                        f"noncommercial_long {row.get('noncomm_positions_long_all')}" if row.get("noncomm_positions_long_all") is not None else "",
                        f"noncommercial_short {row.get('noncomm_positions_short_all')}" if row.get("noncomm_positions_short_all") is not None else "",
                    ]
                    if part
                )
            )
        return [
            SearchResult(
                title=f"CFTC COT public reporting{f' for {market}' if market else ''}",
                url=url,
                snippet="; ".join(snippets),
                published_at=str(rows[0].get("report_date_as_yyyy_mm_dd") or "")[:10] or None,
                source="CFTC Public Reporting",
                raw={"provider": "cftc_cot", "dataset": CFTC_COT_DATASET, "market": market, "rows": rows},
            )
        ]

    def ecb_data_portal(self, claim: str) -> list[SearchResult]:
        """Return mapped ECB SDMX observations for euro-area statistical claims."""
        series = _series_for_claim(claim, ECB_SERIES)
        if not series:
            return []
        flow, key, label = series
        url = _join_url(self.config.ecb_base_url, "data", flow, key) + "?" + urllib.parse.urlencode(
            {"lastNObservations": 3, "format": "csvdata"}
        )
        rows = _parse_observation_csv(self._get_text(url))
        if not rows:
            return []
        return [
            SearchResult(
                title=label,
                url=url,
                snippet=_observation_snippet(rows),
                published_at=rows[0].get("date"),
                source="ECB Data Portal",
                raw={"provider": "ecb_data_portal", "flow": flow, "key": key, "rows": rows},
            )
        ]

    def bis_data_portal(self, claim: str) -> list[SearchResult]:
        """Return mapped BIS SDMX observations for global financial-statistics claims."""
        series = _series_for_claim(claim, BIS_SERIES)
        if not series:
            return []
        flow, key, label = series
        url = _join_url(self.config.bis_base_url, "data", "dataflow", "BIS", flow, "1.0", key) + "?" + urllib.parse.urlencode(
            {"lastNObservations": 3, "format": "csv"}
        )
        rows = _parse_observation_csv(self._get_text(url))
        if not rows:
            return []
        return [
            SearchResult(
                title=label,
                url=url,
                snippet=_observation_snippet(rows),
                published_at=rows[0].get("date"),
                source="BIS Data Portal",
                raw={"provider": "bis_data_portal", "flow": flow, "key": key, "rows": rows},
            )
        ]

    def imf_data_api(
        self,
        claim: str,
        agency: str | None = None,
        dataflow: str | None = None,
        key: str | None = None,
        start_period: str | None = None,
        end_period: str | None = None,
    ) -> list[SearchResult]:
        """Return IMF public SDMX 3.0 observations for mapped or explicit series keys."""
        series = _imf_series_for_claim(claim, agency=agency, dataflow=dataflow, key=key)
        if not series:
            return []
        agency_id, flow, series_key, label = series
        years = _world_bank_date_range_for_claim(claim)
        params: dict[str, str | int] = {
            "dimensionAtObservation": "TIME_PERIOD",
            "attributes": "dsd",
            "measures": "all",
            "includeHistory": "false",
        }
        if start_period:
            params["startPeriod"] = start_period
        elif years:
            params["startPeriod"] = str(years[0])
        if end_period:
            params["endPeriod"] = end_period
        elif years:
            params["endPeriod"] = str(years[1])
        if "startPeriod" not in params and "endPeriod" not in params:
            params["lastNObservations"] = 5

        url = _join_url(self.config.imf_base_url, "data", "dataflow", agency_id, flow, "+", series_key)
        url = url + "?" + urllib.parse.urlencode(params)
        payload = self._get_json(url)
        rows = _parse_sdmx_json_observations(payload)
        start_bound = start_period or (str(years[0]) if years else None)
        end_bound = end_period or (str(years[1]) if years else None)
        rows = _filter_observation_rows(rows, start_bound, end_bound)
        if not rows:
            return []
        return [
            SearchResult(
                title=label,
                url=url,
                snippet=_observation_snippet(rows),
                published_at=rows[0].get("date"),
                source="IMF Data API",
                raw={
                    "provider": "imf_data_api",
                    "agency": agency_id,
                    "dataflow": flow,
                    "key": series_key,
                    "rows": rows,
                },
            )
        ]

    def world_bank_indicators(
        self,
        claim: str,
        country_code: str | None = None,
        indicator_code: str | None = None,
        date_range: tuple[int, int] | None = None,
    ) -> list[SearchResult]:
        """Return World Bank Indicators API v2 observations for country-level claims."""
        country = (country_code or _world_bank_country_for_claim(claim) or "").upper()
        indicator = (indicator_code or _world_bank_indicator_for_claim(claim) or "").upper()
        if not indicator:
            return []
        if not country:
            if not _has_world_bank_context(claim):
                return []
            country = "WLD"

        years = date_range or _world_bank_date_range_for_claim(claim)
        params: dict[str, str | int] = {"format": "json", "per_page": 500 if years else 20}
        if years:
            params["date"] = f"{years[0]}:{years[1]}"
        else:
            params["MRV"] = 5

        url = (
            _join_url(self.config.world_bank_base_url, "country", country, "indicator", indicator)
            + "?"
            + urllib.parse.urlencode(params)
        )
        payload = self._get_json(url)
        rows = _world_bank_rows(payload)
        usable = [row for row in rows if row.get("value") is not None]
        if not usable:
            return []

        latest = usable[0]
        country_name = _nested_text(latest, "country", "value") or country
        indicator_name = _nested_text(latest, "indicator", "value") or indicator
        snippets = []
        for row in usable[:8]:
            row_country = _nested_text(row, "country", "value") or country_name
            snippets.append(f"{row.get('date')}: {row_country} {indicator} {row.get('value')}")
        metadata = payload[0] if isinstance(payload, list) and payload and isinstance(payload[0], dict) else {}
        return [
            SearchResult(
                title=f"World Bank {indicator} for {country_name}",
                url=url,
                snippet=f"{indicator_name}; " + "; ".join(snippets),
                published_at=str(latest.get("date") or ""),
                source="World Bank Indicators API",
                raw={
                    "provider": "world_bank_indicators",
                    "country": country,
                    "indicator": indicator,
                    "metadata": metadata,
                    "rows": usable[:20],
                },
            )
        ]

    def bank_of_england(
        self,
        claim: str,
        date_from: date | str | None = None,
        date_to: date | str | None = None,
    ) -> list[SearchResult]:
        """Return Bank of England IADB CSV rows for mapped UK macro-financial claims."""
        series = _series_for_claim(claim, BOE_SERIES)
        if not series:
            return []
        code, label = series
        start, end = _boe_date_window(claim, date_from, date_to)
        url = self.config.boe_iadb_base_url + "?" + urllib.parse.urlencode(
            {
                "csv.x": "yes",
                "Datefrom": _format_boe_date(start),
                "Dateto": _format_boe_date(end),
                "SeriesCodes": code,
                "UsingCodes": "Y",
                "CSVF": "TN",
                "VPD": "Y",
                "VFD": "N",
            }
        )
        text = self._get_text(url)
        rows = _parse_boe_csv(text, [code]) or _parse_observation_csv(text)
        if not rows:
            return []
        return [
            SearchResult(
                title=label,
                url=url,
                snippet=_observation_snippet(rows),
                published_at=rows[0].get("date"),
                source="Bank of England IADB",
                raw={"provider": "bank_of_england", "series_code": code, "format": "csv", "rows": rows},
            )
        ]

    def openfigi(self, claim: str, ticker: str) -> list[SearchResult]:
        """Return OpenFIGI mapping results for identifier-resolution claims."""
        if not _needs_openfigi_data(claim):
            return []
        id_type, id_value = _openfigi_identifier(claim, ticker)
        body = [{"idType": id_type, "idValue": id_value}]
        if id_type == "TICKER":
            body[0]["exchCode"] = "US"
        headers = {}
        if self.config.openfigi_api_key:
            headers["X-OPENFIGI-APIKEY"] = self.config.openfigi_api_key
        url = "https://api.openfigi.com/v3/mapping"
        data = self._post_json(url, body, headers=headers)
        rows = []
        if isinstance(data, list):
            for block in data:
                if isinstance(block, dict):
                    rows.extend(block.get("data") or [])
        if not rows:
            return []
        snippets = []
        for row in rows[:5]:
            snippets.append(
                f"{row.get('ticker')} {row.get('name')} FIGI {row.get('figi')} compositeFIGI {row.get('compositeFIGI')} "
                f"securityType {row.get('securityType')} marketSector {row.get('marketSector')}"
            )
        return [
            SearchResult(
                title=f"OpenFIGI mapping for {id_type} {id_value}",
                url="https://www.openfigi.com/api",
                snippet="; ".join(snippets),
                source="OpenFIGI",
                raw={"provider": "openfigi", "id_type": id_type, "id_value": id_value, "rows": rows},
            )
        ]

    def finra_query_api(
        self,
        claim: str,
        group: str | None = None,
        dataset: str | None = None,
        as_of_date: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Return FINRA Query API rows for fixed-income and regulatory claims."""
        if not group or not dataset:
            if not _needs_finra_data(claim):
                return []
            mapped = _series_for_claim(claim, FINRA_DATASETS) or FINRA_DATASETS["trace"]
            group, dataset, label = mapped
        else:
            label = f"FINRA {group}/{dataset}"
        token = self._finra_access_token()
        if not token:
            return []
        params: dict[str, str | int] = {"limit": max(1, min(int(limit), 100))}
        if _parse_iso_date(as_of_date):
            params["asOfDate"] = str(as_of_date)[:10]
        url = _join_url("https://api.finra.org", "data", "group", group, "name", dataset)
        url = url + "?" + urllib.parse.urlencode(params)
        try:
            rows = self._get_json_with_headers(
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                return [
                    SearchResult(
                        title=f"{label} unavailable",
                        url=url,
                        snippet=(
                            f"FINRA Query API returned HTTP {exc.code}; the credential may not be entitled "
                            f"for {group}/{dataset}."
                        ),
                        source="FINRA Query API",
                        raw={
                            "provider": "finra_query_api",
                            "group": group,
                            "dataset": dataset,
                            "status_code": exc.code,
                            "error": "finra_entitlement_or_authorization",
                        },
                    )
                ]
            raise
        if isinstance(rows, dict):
            row_list = rows.get("data") if isinstance(rows.get("data"), list) else [rows]
        else:
            row_list = rows if isinstance(rows, list) else []
        row_list = [row for row in row_list if isinstance(row, dict)]
        if not row_list:
            return []
        snippet = "; ".join(_finra_row_summary(row) for row in row_list[:5])
        return [
            SearchResult(
                title=label,
                url=url,
                snippet=snippet,
                published_at=_finra_row_date(row_list[0]),
                source="FINRA Query API",
                raw={"provider": "finra_query_api", "group": group, "dataset": dataset, "rows": row_list[:20]},
            )
        ]

    def marketstack(self, ticker: str) -> list[SearchResult]:
        """Return Marketstack latest end-of-day quote data."""
        key = self.config.marketstack_api_key
        if not key:
            return []
        provider_symbol = _price_provider_symbols(ticker, "marketstack")[0]
        data = self._get_json(
            "https://api.marketstack.com/v1/eod/latest?"
            + urllib.parse.urlencode({"access_key": key, "symbols": provider_symbol.upper(), "limit": 1})
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            return []
        row = rows[0]
        label = _market_price_label(ticker)
        return [
            SearchResult(
                title=f"Marketstack latest EOD price for {label}",
                url=f"https://api.marketstack.com/v1/eod/latest?symbols={provider_symbol.upper()}",
                snippet=f"date {row.get('date')} close {row.get('close')} volume {row.get('volume')}",
                published_at=str(row.get("date", ""))[:10] or None,
                source="Marketstack",
                raw={"provider": "marketstack", "symbol": provider_symbol, "requested_symbol": ticker.upper()},
            )
        ]

    def tiingo(self, ticker: str) -> list[SearchResult]:
        """Return Tiingo recent daily price data."""
        key = self.config.tiingo_api_key
        if not key:
            return []
        provider_symbol = _price_provider_symbols(ticker, "tiingo")[0]
        start = (date.today() - timedelta(days=10)).isoformat()
        url = (
            f"https://api.tiingo.com/tiingo/daily/{provider_symbol.lower()}/prices?"
            + urllib.parse.urlencode({"startDate": start, "token": key})
        )
        data = self._get_json(url)
        if not isinstance(data, list) or not data:
            return []
        row = data[-1]
        label = _market_price_label(ticker)
        return [
            SearchResult(
                title=f"Tiingo latest EOD price for {label}",
                url=f"https://api.tiingo.com/tiingo/daily/{provider_symbol.lower()}/prices",
                snippet=f"date {row.get('date')} close {row.get('close')} adjClose {row.get('adjClose')} volume {row.get('volume')}",
                published_at=str(row.get("date", ""))[:10] or None,
                source="Tiingo",
                raw={"provider": "tiingo", "symbol": provider_symbol, "requested_symbol": ticker.upper()},
            )
        ]

    def stooq(self, ticker: str, as_of_date: str | None = None) -> list[SearchResult]:
        """Return Stooq latest quote data; no API key is required."""
        symbol = _stooq_symbol(ticker)
        url = f"https://stooq.com/q/l/?s={urllib.parse.quote(symbol)}&f=sd2t2ohlcv&h&e=csv"
        text = self._get_text(url)
        rows = list(csv.DictReader(StringIO(text)))
        if not rows:
            return []
        row = rows[0]
        if row.get("Close") in {None, "", "N/D"}:
            return []
        quote_date = _parse_iso_date(row.get("Date"))
        as_of = _parse_iso_date(as_of_date)
        if quote_date and as_of and quote_date > as_of:
            return []
        label = _market_price_label(ticker)
        return [
            SearchResult(
                title=f"Stooq latest quote for {label}",
                url=url,
                snippet=(
                    f"{label} ({ticker.upper()}) latest quote: date {row.get('Date')} "
                    f"close {row.get('Close')} open {row.get('Open')} high {row.get('High')} "
                    f"low {row.get('Low')} volume {row.get('Volume')}"
                ),
                published_at=row.get("Date"),
                source="Stooq",
                raw={"provider": "stooq", "symbol": symbol, "requested_symbol": ticker.upper()},
            )
        ]

    def historical_prices(
        self,
        ticker: str,
        claim: str,
        as_of_date: str | None = None,
    ) -> list[SearchResult]:
        """Return daily historical prices from the first configured provider."""
        lookback_months, start, as_of, window_label, window_source = self._price_history_window(claim, as_of_date)
        self._last_historical_price_errors = []
        providers = [
            ("alpha_vantage_historical_prices", self.alpha_vantage_historical_prices),
            ("fmp_historical_prices", self.fmp_historical_prices),
            ("finnhub_historical_prices", self.finnhub_historical_prices),
            ("fred_historical_prices", self.fred_historical_prices),
            ("stooq_historical_prices", self.stooq_historical_prices),
        ]
        for provider_name, provider in providers:
            for provider_symbol in _price_provider_symbols(ticker, provider_name):
                try:
                    points = provider(provider_symbol, start, as_of)
                except Exception as exc:
                    self._last_historical_price_errors.append(_provider_failure_message(provider_name, exc))
                    continue
                if not points:
                    continue
                return self._price_history_result(
                    ticker=ticker,
                    lookback_months=lookback_months,
                    provider_name=provider_name,
                    url=self._price_history_url(provider_name, provider_symbol, start, as_of),
                    points=points,
                    window_label=window_label,
                    window_source=window_source,
                )
        return []

    def alpha_vantage_historical_prices(
        self,
        ticker: str,
        start: date,
        as_of: date,
    ) -> list[PricePoint]:
        """Return Alpha Vantage daily prices within the requested window."""
        key = self.config.alpha_vantage_api_key
        if not key:
            return []
        url = "https://www.alphavantage.co/query?" + urllib.parse.urlencode(
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker.upper(),
                "outputsize": "full",
                "apikey": key,
            }
        )
        data = self._get_json(url)
        series = data.get("Time Series (Daily)", {}) if isinstance(data, dict) else {}
        points = []
        for day, row in series.items():
            try:
                day_date = date.fromisoformat(day)
                if not start <= day_date <= as_of:
                    continue
                points.append(
                    PricePoint(
                        date=day_date,
                        open=float(row["1. open"]),
                        high=float(row["2. high"]),
                        low=float(row["3. low"]),
                        close=float(row["4. close"]),
                        volume=int(row.get("5. volume", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(points, key=lambda item: item.date)

    def fmp_historical_prices(
        self,
        ticker: str,
        start: date,
        as_of: date,
    ) -> list[PricePoint]:
        """Return FMP historical end-of-day prices within the requested window."""
        key = self.config.fmp_api_key
        if not key:
            return []
        url = "https://financialmodelingprep.com/stable/historical-price-eod/full?" + urllib.parse.urlencode(
            {
                "symbol": ticker.upper(),
                "from": start.isoformat(),
                "to": as_of.isoformat(),
                "apikey": key,
            }
        )
        data = self._get_json(url)
        rows = data.get("historical", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        points = []
        for row in rows:
            try:
                day_date = date.fromisoformat(str(row["date"])[:10])
                if not start <= day_date <= as_of:
                    continue
                points.append(
                    PricePoint(
                        date=day_date,
                        open=float(row.get("open") or row.get("adjOpen") or row["close"]),
                        high=float(row.get("high") or row.get("adjHigh") or row["close"]),
                        low=float(row.get("low") or row.get("adjLow") or row["close"]),
                        close=float(row.get("close") or row.get("adjClose")),
                        volume=int(row.get("volume") or 0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(points, key=lambda item: item.date)

    def finnhub_historical_prices(
        self,
        ticker: str,
        start: date,
        as_of: date,
    ) -> list[PricePoint]:
        """Return Finnhub daily candle prices within the requested window."""
        key = self.config.finnhub_api_key
        if not key:
            return []
        start_ts = int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime.combine(as_of, time.max, tzinfo=timezone.utc).timestamp())
        url = "https://finnhub.io/api/v1/stock/candle?" + urllib.parse.urlencode(
            {
                "symbol": ticker.upper(),
                "resolution": "D",
                "from": start_ts,
                "to": end_ts,
                "token": key,
            }
        )
        data = self._get_json(url)
        if not isinstance(data, dict) or data.get("s") != "ok":
            return []
        timestamps = data.get("t", [])
        points = []
        for idx, timestamp in enumerate(timestamps):
            try:
                points.append(
                    PricePoint(
                        date=datetime.fromtimestamp(timestamp, timezone.utc).date(),
                        open=float(data["o"][idx]),
                        high=float(data["h"][idx]),
                        low=float(data["l"][idx]),
                        close=float(data["c"][idx]),
                        volume=int(data["v"][idx]),
                    )
                )
            except (IndexError, KeyError, TypeError, ValueError):
                continue
        return sorted(points, key=lambda item: item.date)

    def fred_historical_prices(
        self,
        ticker: str,
        start: date,
        as_of: date,
    ) -> list[PricePoint]:
        """Return FRED daily index levels as close-only price points."""
        key = self.config.fred_api_key
        if not key:
            return []
        mapping = FRED_INDEX_PRICE_SERIES.get(str(ticker or "").upper())
        if not mapping:
            return []
        series_id, _label = mapping
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(
            {
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "observation_start": start.isoformat(),
                "observation_end": as_of.isoformat(),
                "sort_order": "asc",
            }
        )
        data = self._get_json(url)
        observations = data.get("observations", []) if isinstance(data, dict) else []
        points: list[PricePoint] = []
        for row in observations:
            try:
                value = str(row.get("value", "")).strip()
                if not value or value == ".":
                    continue
                day = date.fromisoformat(str(row["date"])[:10])
                close = float(value)
                points.append(
                    PricePoint(
                        date=day,
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=0,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(points, key=lambda item: item.date)

    def stooq_historical_prices(
        self,
        ticker: str,
        start: date,
        as_of: date,
    ) -> list[PricePoint]:
        """Return Stooq daily historical prices when CSV download is available."""
        symbol = _stooq_symbol(ticker)
        url = (
            "https://stooq.com/q/d/l/?"
            + urllib.parse.urlencode(
                {
                    "s": symbol,
                    "d1": start.strftime("%Y%m%d"),
                    "d2": as_of.strftime("%Y%m%d"),
                    "i": "d",
                }
            )
        )
        text = self._get_text(url)
        if "get your apikey" in text.lower():
            return []
        return parse_stooq_price_csv(text)

    def _price_history_result(
        self,
        ticker: str,
        lookback_months: int,
        provider_name: str,
        url: str,
        points: list[PricePoint],
        window_label: str | None = None,
        window_source: str | None = None,
    ) -> list[SearchResult]:
        summary = summarize_price_history(points)
        if summary is None:
            return []
        label = _market_price_label(ticker)
        snippet = format_price_history_summary(label, lookback_months, summary)
        if window_label:
            snippet = f"retrieval_window {window_label}; window_source {window_source or 'unknown'}; " + snippet
        return [
            SearchResult(
                title=(
                    f"{_price_history_source_name(provider_name)} "
                    f"{lookback_months}-month historical prices for {label}"
                ),
                url=url,
                snippet=snippet,
                published_at=summary.end_date,
                source=_price_history_source_name(provider_name),
                raw={
                    "provider": provider_name,
                    "lookback_months": lookback_months,
                    "window_label": window_label,
                    "window_source": window_source,
                    "summary": summary.__dict__,
                },
            )
        ]

    def _price_history_window(self, claim: str, as_of_date: str | None) -> tuple[int, date, date, str, str]:
        as_of = _parse_iso_date(as_of_date) or date.today()
        window = infer_price_window(claim, as_of)
        return window.lookback_months, window.start, window.end, window.label, window.source

    def _price_history_url(self, provider_name: str, ticker: str, start: date, as_of: date) -> str:
        if provider_name == "alpha_vantage_historical_prices":
            return f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker.upper()}"
        if provider_name == "fmp_historical_prices":
            return f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker.upper()}"
        if provider_name == "finnhub_historical_prices":
            return f"https://finnhub.io/api/v1/stock/candle?symbol={ticker.upper()}&resolution=D"
        if provider_name == "fred_historical_prices":
            mapping = FRED_INDEX_PRICE_SERIES.get(str(ticker or "").upper())
            series_id = mapping[0] if mapping else ticker.upper()
            return f"https://fred.stlouisfed.org/series/{series_id}"
        symbol = _stooq_symbol(ticker)
        return (
            "https://stooq.com/q/d/l/?"
            + urllib.parse.urlencode(
                {
                    "s": symbol,
                    "d1": start.strftime("%Y%m%d"),
                    "d2": as_of.strftime("%Y%m%d"),
                    "i": "d",
                }
            )
        )

    def yahoo_chart(self, ticker: str) -> list[SearchResult]:
        """Return unofficial Yahoo chart data when fallback is enabled."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker.upper())}?range=5d&interval=1d"
        data = self._get_json(url)
        result = data.get("chart", {}).get("result", []) if isinstance(data, dict) else []
        if not result:
            return []
        meta = result[0].get("meta", {})
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [value for value in quote.get("close", []) if value is not None]
        if not closes:
            return []
        return [
            SearchResult(
                title=f"Yahoo chart fallback for {ticker.upper()}",
                url=url,
                snippet=f"regularMarketPrice {meta.get('regularMarketPrice')} last close {closes[-1]} currency {meta.get('currency')}",
                source="Yahoo Finance unofficial",
                raw={"provider": "yahoo_chart_unofficial"},
            )
        ]

    def _ticker_to_cik(self, ticker: str) -> int | None:
        """Resolve an equity ticker to a SEC CIK using the SEC ticker map."""
        data = self._get_json("https://www.sec.gov/files/company_tickers.json", sec=True)
        target = ticker.upper()
        for item in data.values():
            if str(item.get("ticker", "")).upper() == target:
                return int(item["cik_str"])
        return None

    def _concepts_for_claim(self, claim: str) -> list[str]:
        """Map claim keywords to a small set of SEC us-gaap concepts."""
        if is_corporate_transaction_claim(claim):
            return []
        lower = claim.lower()
        concepts: list[str] = []
        for keyword, mapped in SEC_CONCEPTS.items():
            if keyword in lower:
                concepts.extend(mapped)
        return list(dict.fromkeys(concepts))

    def _matching_sec_concepts(
        self,
        facts_by_taxonomy: dict[str, Any],
        concept_names: list[str],
        claim: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        matches: list[tuple[str, dict[str, Any]]] = []
        preferred = set(concept_names)
        seen = set()
        for taxonomy, taxonomy_facts in facts_by_taxonomy.items():
            if not isinstance(taxonomy_facts, dict):
                continue
            for concept, concept_data in taxonomy_facts.items():
                if concept not in preferred and not _sec_concept_matches_claim(concept, claim):
                    continue
                key = (taxonomy, concept)
                if key in seen:
                    continue
                seen.add(key)
                matches.append((concept, concept_data))
        matches.sort(key=lambda item: (0 if item[0] in preferred else 1, item[0]))
        return matches[:24]

    def _fred_series_for_claim(self, claim: str) -> str | None:
        """Map macro claim keywords to a FRED series id."""
        lower = claim.lower()
        for keyword, series_id in FRED_SERIES.items():
            if _keyword_matches(lower, keyword):
                return series_id
        return None

    def _get_json(self, url: str, sec: bool = False) -> Any:
        """GET a URL and parse the response as JSON."""
        text = self._get_text(url, sec=sec)
        return json.loads(text)

    def _get_json_with_headers(self, url: str, headers: dict[str, str] | None = None) -> Any:
        """GET JSON with caller-supplied headers."""
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.config.sec_user_agent or "CredenceAnalytics/0.1 research@example.com",
                **(headers or {}),
            },
            method="GET",
        )
        with urlopen_request(
            request,
            timeout=self.config.request_timeout,
            allow_insecure_ssl_fallback=self.config.allow_insecure_ssl_fallback,
        ) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _post_json(self, url: str, body: Any, headers: dict[str, str] | None = None) -> Any:
        """POST JSON and parse a JSON response."""
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
            method="POST",
        )
        with urlopen_request(
            request,
            timeout=self.config.request_timeout,
            allow_insecure_ssl_fallback=self.config.allow_insecure_ssl_fallback,
        ) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _post_form_json(self, url: str, body: dict[str, str], headers: dict[str, str] | None = None) -> Any:
        """POST form-encoded data and parse a JSON response."""
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(body).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", **(headers or {})},
            method="POST",
        )
        with urlopen_request(
            request,
            timeout=self.config.request_timeout,
            allow_insecure_ssl_fallback=self.config.allow_insecure_ssl_fallback,
        ) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _finra_access_token(self) -> str | None:
        client_id = self.config.finra_client_id
        client_secret = self.config.finra_client_secret
        if not client_id or not client_secret:
            return None
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        try:
            payload = self._post_form_json(
                "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token",
                {"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {basic}"},
            )
        except urllib.error.HTTPError:
            return None
        if isinstance(payload, dict):
            return str(payload.get("access_token") or "") or None
        return None

    def _get_text(self, url: str, sec: bool = False) -> str:
        """GET a URL as text, adding SEC headers when needed."""
        headers = {
            "Accept": "application/json,text/csv,text/plain,*/*",
            "User-Agent": self.config.sec_user_agent or "CredenceAnalytics/0.1 research@example.com",
        }
        if sec:
            headers["User-Agent"] = self.config.sec_user_agent or "financial-credibility-toolkit/0.1 contact@example.com"
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urlopen_request(
            request,
            timeout=self.config.request_timeout,
            allow_insecure_ssl_fallback=self.config.allow_insecure_ssl_fallback,
        ) as response:
            return response.read().decode("utf-8", errors="replace")


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    """Preserve provider order while dropping duplicate or empty URLs."""
    seen = set()
    deduped = []
    for result in results:
        if not result.url or result.url in seen:
            continue
        seen.add(result.url)
        deduped.append(result)
    return deduped


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _price_history_source_name(provider_name: str) -> str:
    return {
        "alpha_vantage_historical_prices": "Alpha Vantage",
        "fmp_historical_prices": "Financial Modeling Prep",
        "finnhub_historical_prices": "Finnhub",
        "fred_historical_prices": "FRED",
        "stooq_historical_prices": "Stooq",
    }.get(provider_name, provider_name)


def _provider_failure_message(provider_name: str, exc: Exception) -> str:
    label = _price_history_source_name(provider_name)
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return f"{label} rate-limited (HTTP 429)"
        if exc.code in {401, 403}:
            return f"{label} authorization or entitlement failed (HTTP {exc.code})"
        return f"{label} unavailable (HTTP {exc.code})"
    text = str(exc).strip()
    return f"{label} failed{f': {text[:120]}' if text else ''}"


def _join_url(base: str, *parts: str) -> str:
    cleaned = base.rstrip("/")
    suffix = "/".join(urllib.parse.quote(str(part).strip("/"), safe="+") for part in parts if str(part).strip("/"))
    return f"{cleaned}/{suffix}" if suffix else cleaned


def _market_price_label(ticker: str) -> str:
    symbol = str(ticker or "").upper()
    return str(MARKET_PRICE_SYMBOLS.get(symbol, {}).get("label") or symbol)


def _price_provider_symbols(ticker: str, provider_name: str) -> list[str]:
    symbol = str(ticker or "").upper()
    aliases = MARKET_PRICE_SYMBOLS.get(symbol, {})
    provider_key = {
        "alpha_vantage_historical_prices": "alpha_vantage",
        "fmp_historical_prices": "fmp",
        "finnhub_historical_prices": "finnhub",
        "stooq_historical_prices": "stooq",
    }.get(provider_name, provider_name)
    values = aliases.get(provider_key)
    if isinstance(values, list) and values:
        return values
    return [symbol]


def _stooq_symbol(ticker: str) -> str:
    symbol = _price_provider_symbols(ticker, "stooq")[0]
    if symbol.startswith("^") or "." in symbol:
        return symbol.lower()
    return f"{symbol.lower()}.us"


def _provider_allowed(name: str, allowed: set[str]) -> bool:
    if name in allowed:
        return True
    grouped = {
        "company_fundamentals_vendor": {"alpha_vantage", "finnhub", "fmp"},
        "market_prices_vendor": {"marketstack", "tiingo", "stooq", "yahoo_chart_unofficial"},
    }
    return any(name in members for provider, members in grouped.items() if provider in allowed)


def _series_for_claim(claim: str, mapping: dict[str, tuple]) -> tuple | None:
    lower = claim.lower()
    for keyword, series in mapping.items():
        if keyword in lower:
            return series
    return None


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized = keyword.lower().strip()
    if not normalized:
        return False
    if re.search(r"[^a-z0-9 ]", normalized):
        return normalized in text
    pattern = r"\b" + r"[\s-]+".join(re.escape(part) for part in normalized.split()) + r"\b"
    return bool(re.search(pattern, text))


def _year_window_for_claim(claim: str, as_of_date: str | None, default_years: int = 3) -> tuple[int, int]:
    years = _world_bank_date_range_for_claim(claim)
    if years:
        return years
    as_of = _parse_iso_date(as_of_date)
    end_year = as_of.year if as_of else date.today().year
    return max(1900, end_year - max(default_years - 1, 0)), end_year


def _bls_period_label(row: dict[str, Any]) -> str:
    year = str(row.get("year") or "")
    period = str(row.get("period") or "")
    if year and period:
        return f"{year}-{period}"
    return year or period


def _bea_data_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    bea = payload.get("BEAAPI")
    if not isinstance(bea, dict):
        return []
    results = bea.get("Results")
    if isinstance(results, dict):
        data = results.get("Data") or []
        return [row for row in data if isinstance(row, dict)]
    return []


def _first_mapping_match(claim: str, mapping: dict[str, str]) -> str | None:
    lower = claim.lower()
    for keyword, value in mapping.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            return value
    return None


def _needs_finra_data(claim: str) -> bool:
    lower = claim.lower()
    return any(
        keyword in lower
        for keyword in [
            "finra",
            "trace",
            "fixed income",
            "corporate bond",
            "corporate debt",
            "bond trade",
            "bond volume",
            "agency debt",
            "144a",
            "treasury daily aggregates",
            "treasury weekly aggregates",
        ]
    )


def _finra_row_date(row: dict[str, Any]) -> str | None:
    for key in ["tradeReportDate", "tradeDate", "reportDate", "date", "asOfDate"]:
        value = row.get(key)
        if value:
            return str(value)[:10]
    return None


def _finra_row_summary(row: dict[str, Any]) -> str:
    date_value = _finra_row_date(row)
    preferred = [
        "productCategory",
        "tradeType",
        "gradeCode",
        "totalTrades",
        "totalTradeCount",
        "totalTransactions",
        "totalVolume",
        "advances",
        "declines",
        "unchanged",
        "dealerCustomerVolume",
        "atsInterdealerVolume",
        "dealerCustomerCount",
    ]
    parts = [f"{key} {row.get(key)}" for key in preferred if row.get(key) is not None]
    if not parts:
        parts = [f"{key} {value}" for key, value in list(row.items())[:6]]
    return " ".join(part for part in [f"{date_value}:" if date_value else "", *parts] if part)


def _imf_series_for_claim(
    claim: str,
    agency: str | None = None,
    dataflow: str | None = None,
    key: str | None = None,
) -> tuple[str, str, str, str] | None:
    if agency and dataflow and key:
        return agency, dataflow, key, f"IMF {dataflow} {key}"

    direct = re.search(
        r"/data/dataflow/(?P<agency>[^/\s]+)/(?P<flow>[^/\s]+)/(?P<version>[^/\s]+)/(?P<key>[^?\s]+)",
        claim,
    )
    if direct:
        return (
            urllib.parse.unquote(direct.group("agency")),
            urllib.parse.unquote(direct.group("flow")),
            urllib.parse.unquote(direct.group("key")),
            f"IMF {urllib.parse.unquote(direct.group('flow'))} {urllib.parse.unquote(direct.group('key'))}",
        )

    explicit = re.search(
        r"\bIMF[:\s]+(?P<agency>[A-Z][A-Z0-9_.]+)[/:](?P<flow>[A-Z][A-Z0-9_]+)[/:](?P<key>[A-Z0-9_.+]+)\b",
        claim,
        flags=re.IGNORECASE,
    )
    if explicit:
        return (
            explicit.group("agency").upper(),
            explicit.group("flow").upper(),
            explicit.group("key").upper(),
            f"IMF {explicit.group('flow').upper()} {explicit.group('key').upper()}",
        )

    lower = claim.lower()
    if "weo" not in lower and "world economic outlook" not in lower and "imf" not in lower:
        return None
    country = _first_mapping_match(claim, IMF_COUNTRIES)
    indicator = None
    label = None
    for keyword, mapped in IMF_WEO_INDICATORS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            indicator, label = mapped
            break
    if not country or not indicator:
        return None
    series_key = f"{country}.{indicator}.A"
    return "IMF.RES", "WEO", series_key, f"{label} for {country}"


def _parse_observation_csv(text: str) -> list[dict[str, str]]:
    """Parse common SDMX/IADB CSV observation shapes into date/value rows."""
    if not text.strip():
        return []
    rows = []
    for row in csv.DictReader(StringIO(text)):
        date_value = _first_present(row, ["TIME_PERIOD", "time_period", "Date", "DATE", "date", "OBS_DATE"])
        observed = _first_present(row, ["OBS_VALUE", "obs_value", "Value", "VALUE", "value", "IADB Value"])
        if not date_value or observed in {None, ""}:
            continue
        rows.append({"date": str(date_value)[:10], "value": str(observed), "raw": dict(row)})
    return sorted(rows, key=lambda item: item["date"], reverse=True)[:5]


def _first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in {None, ""}:
            return row.get(key)
    for key, value in row.items():
        normalized = key.strip().lower().replace(" ", "_")
        if normalized in {candidate.lower().replace(" ", "_") for candidate in keys} and value not in {None, ""}:
            return value
    return None


def _observation_snippet(rows: list[dict[str, str]]) -> str:
    return "; ".join(f"{row.get('date')}: {row.get('value')}" for row in rows[:5])


def _filter_observation_rows(
    rows: list[dict[str, str]],
    start_period: str | None,
    end_period: str | None,
) -> list[dict[str, str]]:
    if not start_period and not end_period:
        return rows
    filtered = []
    for row in rows:
        period = str(row.get("date") or "")
        if start_period and period < start_period:
            continue
        if end_period and period > end_period:
            continue
        filtered.append(row)
    return filtered


def _parse_sdmx_json_observations(payload: Any) -> list[dict[str, str]]:
    """Parse common SDMX-JSON dataSet/series/observation payloads."""
    container = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if not isinstance(container, dict):
        return []
    datasets = container.get("dataSets") or container.get("datasets") or []
    if not isinstance(datasets, list):
        return []
    dimensions = _sdmx_dimensions(container)
    observation_dimensions = _sdmx_dimension_list(dimensions.get("observation"))
    observation_values = observation_dimensions[0].get("values", []) if observation_dimensions else []

    rows: list[dict[str, str]] = []
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        top_observations = dataset.get("observations")
        if isinstance(top_observations, dict):
            rows.extend(_parse_sdmx_observation_map(top_observations, observation_values, None))
        series_map = dataset.get("series")
        if not isinstance(series_map, dict):
            continue
        for series_key, series_payload in series_map.items():
            if not isinstance(series_payload, dict):
                continue
            observations = series_payload.get("observations")
            if isinstance(observations, dict):
                rows.extend(_parse_sdmx_observation_map(observations, observation_values, str(series_key)))
    return sorted(rows, key=lambda item: item["date"], reverse=True)[:8]


def _sdmx_dimensions(container: dict[str, Any]) -> dict[str, Any]:
    structures = container.get("structures") or container.get("structure") or {}
    if isinstance(structures, list):
        structures = structures[0] if structures and isinstance(structures[0], dict) else {}
    return structures.get("dimensions", {}) if isinstance(structures, dict) else {}


def _sdmx_dimension_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _parse_sdmx_observation_map(
    observations: dict[str, Any],
    observation_values: list[Any],
    series_key: str | None,
) -> list[dict[str, str]]:
    rows = []
    for obs_key, obs_payload in observations.items():
        value = _sdmx_observed_value(obs_payload)
        period = _sdmx_observation_period(str(obs_key), observation_values)
        if value is None or not period:
            continue
        row = {"date": period, "value": str(value), "raw": {"obs_key": obs_key, "obs": obs_payload}}
        if series_key:
            row["series_key"] = series_key
        rows.append(row)
    return rows


def _sdmx_observed_value(obs_payload: Any) -> Any:
    if isinstance(obs_payload, list):
        return obs_payload[0] if obs_payload else None
    if isinstance(obs_payload, dict):
        for key in ("value", "obsValue", "OBS_VALUE"):
            if obs_payload.get(key) not in {None, ""}:
                return obs_payload.get(key)
    return obs_payload


def _sdmx_observation_period(obs_key: str, observation_values: list[Any]) -> str | None:
    first_index = obs_key.split(":")[0]
    try:
        index = int(first_index)
    except ValueError:
        return obs_key or None
    if 0 <= index < len(observation_values):
        item = observation_values[index]
        if isinstance(item, dict):
            return str(item.get("id") or item.get("name") or item.get("value") or obs_key)
        if item not in {None, ""}:
            return str(item)
    return obs_key or None


def _parse_boe_csv(text: str, expected_codes: list[str]) -> list[dict[str, str]]:
    """Parse Bank of England IADB CSVF=TN responses into observation rows."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or any("<title>error</title>" in line.lower() for line in lines[:5]):
        return []
    try:
        reader = csv.DictReader(StringIO("\n".join(lines)))
        fieldnames = reader.fieldnames or []
        if len(fieldnames) < 2:
            return []
        date_field = fieldnames[0]
        rows = []
        for row in reader:
            normalized_date = _normalize_boe_observation_date(str(row.get(date_field) or ""))
            if not normalized_date:
                continue
            for code in expected_codes:
                value = row.get(code)
                if value in {None, ""}:
                    continue
                rows.append({"date": normalized_date, "value": str(value).strip(), "series_code": code, "raw": dict(row)})
        return sorted(rows, key=lambda item: item["date"], reverse=True)[:5]
    except csv.Error:
        return []


def _boe_date_window(
    claim: str,
    date_from: date | str | None,
    date_to: date | str | None,
) -> tuple[date | str, date | str]:
    years = _world_bank_date_range_for_claim(claim)
    if date_from is None and years:
        date_from = date(years[0], 1, 1)
    if date_to is None and years:
        date_to = date(years[1], 12, 31)
    return date_from or date(2020, 1, 1), date_to or "now"


def _format_boe_date(value: date | str) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%b/%Y")
    raw = str(value).strip()
    if raw.lower() == "now":
        return "now"
    parsed = _parse_iso_date(raw)
    if parsed:
        return parsed.strftime("%d/%b/%Y")
    return raw


def _normalize_boe_observation_date(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    for pattern in ("%d %b %Y", "%d/%b/%Y", "%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return raw


def _world_bank_indicator_for_claim(claim: str) -> str | None:
    direct = re.search(r"\b[A-Z]{2,}(?:\.[A-Z0-9]+){2,}\b", claim)
    if direct:
        return direct.group(0)
    return _first_mapping_match(claim, WORLD_BANK_INDICATORS)


def _world_bank_country_for_claim(claim: str) -> str | None:
    match = re.search(r"\bcountry/([A-Za-z0-9]{2,3}|all)\b", claim)
    if match:
        return match.group(1)
    return _first_mapping_match(claim, WORLD_BANK_COUNTRIES)


def _world_bank_date_range_for_claim(claim: str) -> tuple[int, int] | None:
    years = [int(item) for item in re.findall(r"\b(?:19|20)\d{2}\b", claim)]
    if len(years) >= 2:
        first, second = years[0], years[1]
        return (min(first, second), max(first, second))
    if len(years) == 1:
        return (years[0], years[0])
    return None


def _has_world_bank_context(claim: str) -> bool:
    lower = claim.lower()
    return any(
        phrase in lower
        for phrase in [
            "world bank",
            "wdi",
            "world development indicator",
            "world development indicators",
            "international debt statistics",
            "country indicator",
            "country-level",
            "countries",
            "global",
        ]
    )


def _world_bank_rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
    usable = [row for row in rows if isinstance(row, dict)]
    return sorted(usable, key=lambda row: str(row.get("date") or ""), reverse=True)


def _nested_text(row: dict[str, Any], outer: str, inner: str) -> str | None:
    value = row.get(outer)
    if isinstance(value, dict) and value.get(inner) not in {None, ""}:
        return str(value.get(inner))
    return None


def _needs_treasury_data(claim: str) -> bool:
    lower = claim.lower()
    return any(
        phrase in lower
        for phrase in ["federal debt", "public debt", "debt held by the public", "fiscal deficit", "treasury debt"]
    )


def _needs_gleif_data(claim: str) -> bool:
    lower = claim.lower()
    return any(phrase in lower for phrase in ["lei", "legal entity", "counterparty", "issuer identity"])


def _needs_cftc_data(claim: str) -> bool:
    lower = claim.lower()
    return any(
        phrase in lower
        for phrase in ["cftc", "cot", "commitments of traders", "futures positioning", "open interest", "noncommercial"]
    )


def _needs_openfigi_data(claim: str) -> bool:
    lower = claim.lower()
    return any(
        phrase in lower
        for phrase in ["figi", "openfigi", "isin", "cusip", "sedol", "security identifier", "ticker mapping"]
    )


def _openfigi_identifier(claim: str, ticker: str) -> tuple[str, str]:
    patterns = [
        ("ID_ISIN", r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b"),
        ("ID_CUSIP", r"\b([A-Z0-9]{9})\b"),
        ("ID_SEDOL", r"\b([A-Z0-9]{7})\b"),
    ]
    for id_type, pattern in patterns:
        match = re.search(pattern, claim.upper())
        if match:
            return id_type, match.group(1)
    return "TICKER", ticker.upper()


def _sec_concept_matches_claim(concept: str, claim: str) -> bool:
    concept_tokens = set(_tokenize_concept(concept))
    claim_tokens = {token for token in re.split(r"[^a-z0-9]+", claim.lower()) if len(token) > 2}
    if not concept_tokens or not claim_tokens:
        return False
    if "revenue" in concept_tokens and {"revenue", "sales"} & claim_tokens:
        specific_claim_tokens = claim_tokens - {
            "the",
            "and",
            "for",
            "with",
            "from",
            "total",
            "revenue",
            "sales",
            "reported",
            "latest",
            "quarter",
            "year",
            "fiscal",
        }
        if specific_claim_tokens and concept_tokens & specific_claim_tokens:
            return True
    return False


def _tokenize_concept(concept: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", concept)
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", spaced) if len(token) > 2]
