from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from typing import Any

from .config import ToolkitConfig
from .models import ArgumentType, SearchResult
from .net import urlopen_request


SEC_CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "sales": ["Revenues", "SalesRevenueNet"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "earnings": ["NetIncomeLoss", "EarningsPerShareDiluted"],
    "net income": ["NetIncomeLoss"],
    "margin": ["GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss", "Revenues"],
    "cash flow": ["NetCashProvidedByUsedInOperatingActivities", "FreeCashFlow"],
    "assets": ["Assets", "AssetsCurrent"],
    "liabilities": ["Liabilities", "LiabilitiesCurrent"],
    "debt": ["LongTermDebt", "ShortTermBorrowings"],
}

FRED_SERIES = {
    "inflation": "CPIAUCSL",
    "cpi": "CPIAUCSL",
    "interest": "FEDFUNDS",
    "fed funds": "FEDFUNDS",
    "rate": "FEDFUNDS",
    "gdp": "GDP",
    "unemployment": "UNRATE",
    "treasury": "DGS10",
    "yield": "DGS10",
}


@dataclass
class FreeDataSourceClient:
    config: ToolkitConfig

    def query(
        self,
        claim: str,
        ticker: str,
        argument_type: ArgumentType,
        max_results: int = 8,
    ) -> tuple[list[SearchResult], list[str]]:
        results: list[SearchResult] = []
        notes: list[str] = []

        providers = [
            ("sec_company_facts", lambda: self.sec_company_facts(claim, ticker)),
            ("sec_recent_filings", lambda: self.sec_recent_filings(ticker)),
            ("alpha_vantage", lambda: self.alpha_vantage(ticker)),
            ("finnhub", lambda: self.finnhub(ticker)),
            ("fmp", lambda: self.fmp(ticker)),
            ("fred", lambda: self.fred(claim)),
            ("marketstack", lambda: self.marketstack(ticker)),
            ("tiingo", lambda: self.tiingo(ticker)),
            ("stooq", lambda: self.stooq(ticker)),
        ]
        if self.config.enable_yahoo_fallback:
            providers.append(("yahoo_chart_unofficial", lambda: self.yahoo_chart(ticker)))

        for name, provider in providers:
            if len(results) >= max_results:
                break
            try:
                provider_results = provider()
                results.extend(provider_results)
                if provider_results:
                    notes.append(f"{name}: {len(provider_results)} result(s)")
            except Exception as exc:
                notes.append(f"{name} failed: {exc}")

        return _dedupe(results)[:max_results], notes

    def sec_company_facts(self, claim: str, ticker: str) -> list[SearchResult]:
        cik = self._ticker_to_cik(ticker)
        if cik is None:
            return []
        data = self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", sec=True)
        facts = data.get("facts", {}).get("us-gaap", {})
        concept_names = self._concepts_for_claim(claim)
        snippets = []
        latest_date = None

        for concept in concept_names:
            concept_data = facts.get(concept)
            if not concept_data:
                continue
            units = concept_data.get("units", {})
            for unit_name, values in units.items():
                clean_values = [
                    value
                    for value in values
                    if value.get("val") is not None and value.get("filed")
                ]
                clean_values.sort(key=lambda value: value.get("filed", ""), reverse=True)
                for value in clean_values[:2]:
                    latest_date = max(latest_date or "", value.get("filed", "")) or latest_date
                    snippets.append(
                        f"{concept} ({unit_name}) {value.get('fy', '')} {value.get('fp', '')}: "
                        f"{value.get('val')} filed {value.get('filed')} form {value.get('form')}"
                    )

        if not snippets:
            return []

        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        return [
            SearchResult(
                title=f"SEC Company Facts for {ticker.upper()}",
                url=url,
                snippet="; ".join(snippets[:8]),
                published_at=latest_date,
                source="SEC EDGAR",
                raw={"provider": "sec_company_facts", "cik": cik},
            )
        ]

    def sec_recent_filings(self, ticker: str) -> list[SearchResult]:
        cik = self._ticker_to_cik(ticker)
        if cik is None:
            return []
        data = self._get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", sec=True)
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

    def fred(self, claim: str) -> list[SearchResult]:
        key = self.config.fred_api_key
        if not key:
            return []
        series_id = self._fred_series_for_claim(claim)
        if not series_id:
            return []
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(
            {
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 3,
            }
        )
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
                raw={"provider": "fred", "series_id": series_id},
            )
        ]

    def marketstack(self, ticker: str) -> list[SearchResult]:
        key = self.config.marketstack_api_key
        if not key:
            return []
        data = self._get_json(
            "https://api.marketstack.com/v1/eod/latest?"
            + urllib.parse.urlencode({"access_key": key, "symbols": ticker.upper(), "limit": 1})
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            return []
        row = rows[0]
        return [
            SearchResult(
                title=f"Marketstack latest EOD price for {ticker.upper()}",
                url=f"https://api.marketstack.com/v1/eod/latest?symbols={ticker.upper()}",
                snippet=f"date {row.get('date')} close {row.get('close')} volume {row.get('volume')}",
                published_at=str(row.get("date", ""))[:10] or None,
                source="Marketstack",
                raw={"provider": "marketstack"},
            )
        ]

    def tiingo(self, ticker: str) -> list[SearchResult]:
        key = self.config.tiingo_api_key
        if not key:
            return []
        start = (date.today() - timedelta(days=10)).isoformat()
        url = (
            f"https://api.tiingo.com/tiingo/daily/{ticker.lower()}/prices?"
            + urllib.parse.urlencode({"startDate": start, "token": key})
        )
        data = self._get_json(url)
        if not isinstance(data, list) or not data:
            return []
        row = data[-1]
        return [
            SearchResult(
                title=f"Tiingo latest EOD price for {ticker.upper()}",
                url=f"https://api.tiingo.com/tiingo/daily/{ticker.lower()}/prices",
                snippet=f"date {row.get('date')} close {row.get('close')} adjClose {row.get('adjClose')} volume {row.get('volume')}",
                published_at=str(row.get("date", ""))[:10] or None,
                source="Tiingo",
                raw={"provider": "tiingo"},
            )
        ]

    def stooq(self, ticker: str) -> list[SearchResult]:
        symbol = f"{ticker.lower()}.us"
        url = f"https://stooq.com/q/l/?s={urllib.parse.quote(symbol)}&f=sd2t2ohlcv&h&e=csv"
        text = self._get_text(url)
        rows = list(csv.DictReader(StringIO(text)))
        if not rows:
            return []
        row = rows[0]
        if row.get("Close") in {None, "", "N/D"}:
            return []
        return [
            SearchResult(
                title=f"Stooq latest quote for {ticker.upper()}",
                url=url,
                snippet=f"date {row.get('Date')} close {row.get('Close')} open {row.get('Open')} high {row.get('High')} low {row.get('Low')} volume {row.get('Volume')}",
                published_at=row.get("Date"),
                source="Stooq",
                raw={"provider": "stooq"},
            )
        ]

    def yahoo_chart(self, ticker: str) -> list[SearchResult]:
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
        data = self._get_json("https://www.sec.gov/files/company_tickers.json", sec=True)
        target = ticker.upper()
        for item in data.values():
            if str(item.get("ticker", "")).upper() == target:
                return int(item["cik_str"])
        return None

    def _concepts_for_claim(self, claim: str) -> list[str]:
        lower = claim.lower()
        concepts: list[str] = []
        for keyword, mapped in SEC_CONCEPTS.items():
            if keyword in lower:
                concepts.extend(mapped)
        if not concepts:
            concepts = [
                "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "NetIncomeLoss",
                "EarningsPerShareDiluted",
            ]
        return list(dict.fromkeys(concepts))

    def _fred_series_for_claim(self, claim: str) -> str | None:
        lower = claim.lower()
        for keyword, series_id in FRED_SERIES.items():
            if keyword in lower:
                return series_id
        return None

    def _get_json(self, url: str, sec: bool = False) -> Any:
        text = self._get_text(url, sec=sec)
        return json.loads(text)

    def _get_text(self, url: str, sec: bool = False) -> str:
        headers = {"Accept": "application/json,text/csv,text/plain,*/*"}
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
    seen = set()
    deduped = []
    for result in results:
        if not result.url or result.url in seen:
            continue
        seen.add(result.url)
        deduped.append(result)
    return deduped
