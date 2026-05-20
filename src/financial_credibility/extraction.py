from __future__ import annotations

import urllib.parse
import urllib.request
from dataclasses import dataclass

from .config import ToolkitConfig
from .models import Evidence, SearchResult, clamp
from .net import urlopen_request
from .sources import assess_source, score_numeric_consistency, score_recency
from .text import token_overlap


COMPANY_ALIASES = {
    "AAPL": ["apple"],
    "MSFT": ["microsoft"],
    "NVDA": ["nvidia"],
    "TSLA": ["tesla"],
    "AMZN": ["amazon"],
    "GOOGL": ["alphabet", "google"],
    "GOOG": ["alphabet", "google"],
    "META": ["meta", "facebook"],
    "JPM": ["jpmorgan", "jp morgan", "jpmorgan chase"],
    "BAC": ["bank of america"],
    "XOM": ["exxon", "exxonmobil"],
    "CVX": ["chevron"],
    "NFLX": ["netflix"],
}


@dataclass
class EvidenceExtractor:
    config: ToolkitConfig

    def extract(
        self,
        claim: str,
        ticker: str,
        search_results: list[SearchResult],
        as_of_date: str,
        max_sources: int = 8,
    ) -> tuple[list[Evidence], list[str]]:
        evidence: list[Evidence] = []
        notes: list[str] = []

        for result in search_results[:max_sources]:
            text = result.snippet or ""
            if self.config.enable_live_extraction and result.url:
                live_text = self._read_with_jina(result.url)
                if live_text:
                    text = live_text

            source = assess_source(result.url, result.title)
            recency_score, recency_notes = score_recency(result.published_at, as_of_date)
            numeric_score, numeric_notes = score_numeric_consistency(claim, f"{result.title}\n{text}")
            relevance = score_relevance(claim, ticker, result.title, text, result.url)
            entity_match = score_entity_match(ticker, result.title, text, result.url)

            item = Evidence(
                url=result.url,
                title=result.title,
                text=text,
                source_type=source.source_type,
                source_tier=source.source_tier,
                domain=source.domain,
                published_at=result.published_at,
                source_authority=source.authority_score,
                recency_score=recency_score,
                relevance_score=relevance,
                entity_match_score=entity_match,
                numeric_consistency_score=numeric_score,
                notes=source.reasons + recency_notes + numeric_notes,
            )
            evidence.append(item)

        if self.config.enable_live_extraction and not self.config.jina_api_key:
            notes.append("live extraction enabled without JINA_API_KEY; using public reader or snippets")

        return evidence, notes

    def _read_with_jina(self, url: str) -> str:
        jina_url = "https://r.jina.ai/" + urllib.parse.quote(url, safe=":/?&=%")
        headers = {}
        if self.config.jina_api_key:
            headers["Authorization"] = f"Bearer {self.config.jina_api_key}"
        request = urllib.request.Request(jina_url, headers=headers, method="GET")
        try:
            with urlopen_request(
                request,
                timeout=self.config.request_timeout,
                allow_insecure_ssl_fallback=self.config.allow_insecure_ssl_fallback,
            ) as response:
                return response.read().decode("utf-8", errors="replace")[:8000]
        except Exception:
            return ""


def score_relevance(claim: str, ticker: str, title: str, text: str, url: str) -> float:
    overlap = token_overlap(claim, f"{title}\n{text}")
    ticker_bonus = 0.20 if _contains_entity(ticker, title, text, url) else 0.0
    return round(clamp(0.20 + overlap * 0.85 + ticker_bonus), 3)


def score_entity_match(ticker: str, title: str, text: str, url: str) -> float:
    if _contains_entity(ticker, title, text, url):
        return 0.90
    return 0.45


def _contains_entity(ticker: str, title: str, text: str, url: str) -> bool:
    haystack = f"{title} {text} {url}".lower()
    normalized = ticker.upper()
    if normalized.lower() in haystack:
        return True
    return any(alias in haystack for alias in COMPANY_ALIASES.get(normalized, []))
