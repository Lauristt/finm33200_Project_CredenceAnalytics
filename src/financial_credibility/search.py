"""Retrieval layer for evidence candidates.

This module returns `SearchResult` objects only. It does not score sources or
judge claims; that work is centralized in extraction, judging, and aggregation.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import ToolkitConfig
from .data_sources import FreeDataSourceClient
from .models import ArgumentType, SearchResult
from .net import urlopen_request


@dataclass
class SearchClient:
    """Search facade combining prefetched results, structured APIs, and Serper."""

    config: ToolkitConfig
    extra_queries: list[str] = field(default_factory=list)

    def search_financial_sources(
        self,
        claim: str,
        ticker: str,
        argument_type: ArgumentType,
        max_sources: int = 8,
        as_of_date: str | None = None,
        prefetched_results: list[dict[str, Any] | SearchResult] | None = None,
        selected_sources: list[str] | None = None,
    ) -> tuple[list[SearchResult], list[str]]:
        """Retrieve candidate sources for one claim.

        Retrieval order is deliberate: tests/demos can pass `prefetched_results`;
        otherwise structured sources are tried before optional web search.
        The returned notes are surfaced in `EvidencePack.metadata`.
        """
        if prefetched_results is not None:
            return [_normalize_result(item) for item in prefetched_results][:max_sources], ["used prefetched results"]

        results: list[SearchResult] = []
        notes: list[str] = []
        seen_urls: set[str] = set()

        if self.config.enable_structured_sources:
            structured_results, structured_notes = FreeDataSourceClient(self.config).query(
                claim=claim,
                ticker=ticker,
                argument_type=argument_type,
                max_results=max_sources,
                as_of_date=as_of_date,
                allowed_sources=selected_sources,
            )
            notes.extend(structured_notes)
            for result in structured_results:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
                if len(results) >= max_sources:
                    return results, notes

        allow_web_search = selected_sources is None or "serper_web" in selected_sources
        if not self.config.serper_api_key or not allow_web_search:
            if not results:
                if not allow_web_search:
                    notes.append("web search skipped by source selection policy")
                else:
                    notes.append("SERPER_API_KEY not configured and no search results from structured free sources")
            return results, notes

        queries = build_queries(claim, ticker, argument_type) + self.extra_queries
        per_query = max(2, min(5, max_sources))
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
        """Call Serper and normalize organic results into `SearchResult`."""
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
        with urlopen_request(
            request,
            timeout=self.config.request_timeout,
            allow_insecure_ssl_fallback=self.config.allow_insecure_ssl_fallback,
        ) as response:
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
    """Create search queries tailored to the claim's argument type."""
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
    """Accept either dict fixtures or already-normalized search results."""
    if isinstance(item, SearchResult):
        return item
    raw = dict(item.get("raw") or item)
    return SearchResult(
        title=str(item.get("title", "")),
        url=str(item.get("url") or item.get("link") or ""),
        snippet=str(item.get("snippet") or item.get("summary") or item.get("text") or ""),
        published_at=item.get("published_at") or item.get("date"),
        source=item.get("source"),
        raw=raw,
    )
