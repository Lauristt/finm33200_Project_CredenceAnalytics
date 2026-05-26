"""Entity resolution helpers for official-source verification."""

from __future__ import annotations

import re
from typing import Any

from .models import EntityResolution, Evidence, SearchResult


def resolve_entity(
    ticker: str,
    evidence: list[Evidence] | None = None,
    search_results: list[SearchResult] | None = None,
    cik: str | int | None = None,
    lei: str | None = None,
    figi: str | None = None,
) -> EntityResolution:
    """Resolve the core entity identifiers already available in the pipeline."""
    normalized_ticker = ticker.upper()
    discovered_cik = (
        _normalize_cik(cik)
        or _find_raw_identifier(search_results or [], "cik")
        or _find_cik_in_search_results(search_results or [])
        or _find_cik_in_evidence(evidence or [])
    )
    discovered_lei = lei or _find_raw_identifier(search_results or [], "lei")
    sources = []
    issues = []

    if discovered_cik:
        sources.append("SEC")
    if discovered_lei:
        sources.append("GLEIF")
    if figi:
        sources.append("FIGI")
    if evidence and any(item.entity_match_score >= 0.75 for item in evidence):
        sources.append("evidence_entity_match")

    confidence = 0.55
    if normalized_ticker:
        confidence = 0.65
    if discovered_cik:
        confidence = max(confidence, 0.85)
    if discovered_cik and discovered_lei:
        confidence = 0.95
    if evidence and evidence and max(item.entity_match_score for item in evidence) < 0.50:
        confidence = min(confidence, 0.45)
        issues.append("low_evidence_entity_match")

    entity_id = discovered_lei or (f"CIK{discovered_cik}" if discovered_cik else normalized_ticker)
    if not discovered_cik and not discovered_lei:
        issues.append("ticker_only_entity_resolution")

    return EntityResolution(
        ticker=normalized_ticker,
        entity_id=entity_id,
        cik=discovered_cik,
        lei=discovered_lei,
        figi=figi,
        confidence=round(confidence, 3),
        sources=_dedupe(sources),
        issues=issues,
    )


def _find_raw_identifier(results: list[SearchResult], key: str) -> str | None:
    for result in results:
        value = _deep_get(result.raw, key)
        if value:
            return _normalize_cik(value) if key == "cik" else str(value)
    return None


def _find_cik_in_search_results(results: list[SearchResult]) -> str | None:
    for result in results:
        cik = _find_cik_in_text(f"{result.url} {result.snippet}")
        if cik:
            return cik
    return None


def _find_cik_in_evidence(evidence: list[Evidence]) -> str | None:
    for item in evidence:
        cik = _find_cik_in_text(f"{item.url} {item.text}")
        if cik:
            return cik
    return None


def _find_cik_in_text(text: str) -> str | None:
    patterns = [
        r"CIK(\d{1,10})",
        r"/Archives/edgar/data/(\d{1,10})/",
        r"/edgar/data/(\d{1,10})/",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _normalize_cik(match.group(1))
    return None


def _deep_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = _deep_get(nested, key)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _deep_get(nested, key)
            if found:
                return found
    return None


def _normalize_cik(value: str | int | None) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(10) if digits else None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
