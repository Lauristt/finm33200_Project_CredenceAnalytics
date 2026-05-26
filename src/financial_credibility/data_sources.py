"""Structured free/free-tier financial data retrieval.

Provider methods return `SearchResult` objects so the rest of the pipeline can
score all sources through the same extraction and judging path. API keys are
read from `ToolkitConfig`; missing keys simply disable that provider.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from typing import Any

from .config import ToolkitConfig
from .models import ArgumentType, SearchResult
from .net import urlopen_request
from .price_history import (
    PricePoint,
    format_price_history_summary,
    needs_historical_price_data,
    parse_lookback_months,
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
            ("sec_company_facts", lambda: self.sec_company_facts(claim, ticker)),
            ("sec_recent_filings", lambda: self.sec_recent_filings(ticker)),
            ("alpha_vantage", lambda: self.alpha_vantage(ticker)),
            ("finnhub", lambda: self.finnhub(ticker)),
            ("fmp", lambda: self.fmp(ticker)),
            ("fred", lambda: self.fred(claim)),
            ("treasury_fiscal_data", lambda: self.treasury_fiscal_data(claim)),
            ("gleif_entity", lambda: self.gleif_entity(claim, ticker)),
            ("marketstack", lambda: self.marketstack(ticker)),
            ("tiingo", lambda: self.tiingo(ticker)),
            ("stooq", lambda: self.stooq(ticker)),
        ]
        if self.config.enable_yahoo_fallback:
            providers.append(("yahoo_chart_unofficial", lambda: self.yahoo_chart(ticker)))

        for name, provider in providers:
            if len(results) >= max_results:
                break
            if allowed and not _provider_allowed(name, allowed):
                continue
            if name == "historical_prices" and not needs_historical_price_data(claim):
                continue
            try:
                provider_results = provider()
                results.extend(provider_results)
                if provider_results:
                    notes.append(f"{name}: {len(provider_results)} result(s)")
            except Exception as exc:
                notes.append(f"{name} failed: {exc}")

        return _dedupe(results)[:max_results], notes

    def sec_company_facts(self, claim: str, ticker: str) -> list[SearchResult]:
        """Return recent SEC XBRL facts for concepts implied by the claim."""
        cik = self._ticker_to_cik(ticker)
        if cik is None:
            return []
        data = self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", sec=True)
        from datetime import date

        facts_by_taxonomy = data.get("facts", {})
        concept_names = self._concepts_for_claim(claim)
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

    def sec_recent_filings(self, ticker: str) -> list[SearchResult]:
        """Return recent SEC 10-K, 10-Q, and 8-K filings for the ticker."""
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

    def fred(self, claim: str) -> list[SearchResult]:
        """Return a FRED macro series when the claim contains a known keyword."""
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
                raw={"provider": "fred", "series_id": series_id, "observations": observations},
            )
        ]

    def treasury_fiscal_data(self, claim: str) -> list[SearchResult]:
        """Return U.S. Treasury fiscal data for federal debt/fiscal claims."""
        if not _needs_treasury_data(claim):
            return []
        url = (
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
            "v2/accounting/od/debt_to_penny?"
            + urllib.parse.urlencode({"sort": "-record_date", "page[size]": 3})
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

    def marketstack(self, ticker: str) -> list[SearchResult]:
        """Return Marketstack latest end-of-day quote data."""
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
        """Return Tiingo recent daily price data."""
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
        """Return Stooq latest quote data; no API key is required."""
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

    def historical_prices(
        self,
        ticker: str,
        claim: str,
        as_of_date: str | None = None,
    ) -> list[SearchResult]:
        """Return daily historical prices from the first configured provider."""
        lookback_months, start, as_of = self._price_history_window(claim, as_of_date)
        providers = [
            ("alpha_vantage_historical_prices", self.alpha_vantage_historical_prices),
            ("fmp_historical_prices", self.fmp_historical_prices),
            ("finnhub_historical_prices", self.finnhub_historical_prices),
            ("stooq_historical_prices", self.stooq_historical_prices),
        ]
        for provider_name, provider in providers:
            try:
                points = provider(ticker, start, as_of)
            except Exception:
                continue
            if not points:
                continue
            return self._price_history_result(
                ticker=ticker,
                lookback_months=lookback_months,
                provider_name=provider_name,
                url=self._price_history_url(provider_name, ticker, start, as_of),
                points=points,
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

    def stooq_historical_prices(
        self,
        ticker: str,
        start: date,
        as_of: date,
    ) -> list[PricePoint]:
        """Return Stooq daily historical prices when CSV download is available."""
        symbol = f"{ticker.lower()}.us"
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
    ) -> list[SearchResult]:
        summary = summarize_price_history(points)
        if summary is None:
            return []
        return [
            SearchResult(
                title=(
                    f"{_price_history_source_name(provider_name)} "
                    f"{lookback_months}-month historical prices for {ticker.upper()}"
                ),
                url=url,
                snippet=format_price_history_summary(ticker, lookback_months, summary),
                published_at=summary.end_date,
                source=_price_history_source_name(provider_name),
                raw={
                    "provider": provider_name,
                    "lookback_months": lookback_months,
                    "summary": summary.__dict__,
                },
            )
        ]

    def _price_history_window(self, claim: str, as_of_date: str | None) -> tuple[int, date, date]:
        lookback_months = parse_lookback_months(claim)
        as_of = _parse_iso_date(as_of_date) or date.today()
        start = as_of - timedelta(days=max(31, int(lookback_months * 31)))
        return lookback_months, start, as_of

    def _price_history_url(self, provider_name: str, ticker: str, start: date, as_of: date) -> str:
        if provider_name == "alpha_vantage_historical_prices":
            return f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker.upper()}"
        if provider_name == "fmp_historical_prices":
            return f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker.upper()}"
        if provider_name == "finnhub_historical_prices":
            return f"https://finnhub.io/api/v1/stock/candle?symbol={ticker.upper()}&resolution=D"
        symbol = f"{ticker.lower()}.us"
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
            if keyword in lower:
                return series_id
        return None

    def _get_json(self, url: str, sec: bool = False) -> Any:
        """GET a URL and parse the response as JSON."""
        text = self._get_text(url, sec=sec)
        return json.loads(text)

    def _get_text(self, url: str, sec: bool = False) -> str:
        """GET a URL as text, adding SEC headers when needed."""
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
        "stooq_historical_prices": "Stooq",
    }.get(provider_name, provider_name)


def _provider_allowed(name: str, allowed: set[str]) -> bool:
    if name in allowed:
        return True
    grouped = {
        "company_fundamentals_vendor": {"alpha_vantage", "finnhub", "fmp"},
        "market_prices_vendor": {"marketstack", "tiingo", "stooq", "yahoo_chart_unofficial"},
    }
    return any(name in members for provider, members in grouped.items() if provider in allowed)


def _needs_treasury_data(claim: str) -> bool:
    lower = claim.lower()
    return any(
        phrase in lower
        for phrase in ["federal debt", "public debt", "debt held by the public", "fiscal deficit", "treasury debt"]
    )


def _needs_gleif_data(claim: str) -> bool:
    lower = claim.lower()
    return any(phrase in lower for phrase in ["lei", "legal entity", "counterparty", "issuer identity"])


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
