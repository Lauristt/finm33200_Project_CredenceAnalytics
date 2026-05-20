from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import ToolkitConfig
from .models import ArgumentType, SearchResult


@dataclass
class SearchClient:
    config: ToolkitConfig
    extra_queries: list[str] = field(default_factory=list)

    def search_financial_sources(
        self,
        claim: str,
        ticker: str,
        argument_type: ArgumentType,
        max_sources: int = 8,
        prefetched_results: list[dict[str, Any] | SearchResult] | None = None,
    ) -> tuple[list[SearchResult], list[str]]:
        if prefetched_results is not None:
            return [_normalize_result(item) for item in prefetched_results][:max_sources], ["used prefetched results"]

        if not self.config.serper_api_key:
            return [], ["SERPER_API_KEY not configured and no prefetched results supplied"]

        queries = build_queries(claim, ticker, argument_type) + self.extra_queries
        per_query = max(2, min(5, max_sources))
        results: list[SearchResult] = []
        notes: list[str] = []
        seen_urls: set[str] = set()

        for query in queries:
            try:
                for result in self._serper_search(query, per_query):
                    if result.url in seen_urls:
                        continue
                    seen_urls.add(result.url)
                    results.append(result)
                    if len(results) >= max_sources:
                        return results, notes
            except Exception as exc:
                notes.append(f"search failed for query={query!r}: {exc}")

        return results, notes

    def _serper_search(self, query: str, num_results: int) -> list[SearchResult]:
        body = {"q": query, "num": num_results}
        request = urllib.request.Request(
            "https://google.serper.dev/search",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "X-API-KEY": self.config.serper_api_key or "",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = []
        for item in data.get("organic", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    published_at=item.get("date"),
                    source=item.get("source"),
                    raw=item,
                )
            )
        return results


def build_queries(claim: str, ticker: str, argument_type: ArgumentType) -> list[str]:
    base = f'{ticker} "{claim}"'
    if argument_type == ArgumentType.METRIC_FACT:
        return [
            f"{base} SEC 10-Q 10-K",
            f"{ticker} earnings release revenue EPS investor relations",
            f"{ticker} company facts SEC revenue earnings",
        ]
    if argument_type == ArgumentType.EVENT_FACT:
        return [
            f"{base} official announcement investor relations",
            f"{ticker} 8-K SEC filing {claim}",
            f"{ticker} Reuters Bloomberg {claim}",
        ]
    if argument_type == ArgumentType.ATTRIBUTION_FACT:
        return [
            base,
            f"{ticker} analyst rating price target original source",
            f"{ticker} {claim} Reuters Bloomberg",
        ]
    if argument_type == ArgumentType.FORECAST:
        return [
            f"{base} guidance outlook consensus estimates",
            f"{ticker} forecast assumptions guidance investor relations",
            f"{ticker} analyst estimates forecast independent sources",
        ]
    return [
        f"{base} analysis data valuation",
        f"{ticker} valuation analysis revenue margins cash flow",
        f"{ticker} bull bear thesis independent analysis",
    ]


def _normalize_result(item: dict[str, Any] | SearchResult) -> SearchResult:
    if isinstance(item, SearchResult):
        return item
    return SearchResult(
        title=str(item.get("title", "")),
        url=str(item.get("url") or item.get("link") or ""),
        snippet=str(item.get("snippet") or item.get("summary") or item.get("text") or ""),
        published_at=item.get("published_at") or item.get("date"),
        source=item.get("source"),
        raw=dict(item),
    )
