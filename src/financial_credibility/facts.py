"""Canonical fact construction from retrieval and evidence objects."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from .entity import resolve_entity
from .models import CanonicalFact, EntityResolution, Evidence, SearchResult
from .sources import assess_source, extract_numbers


_SEC_FACT_RE = re.compile(
    r"(?P<concept>[A-Za-z][A-Za-z0-9]+)\s+\((?P<unit>[^)]+)\)\s+"
    r"(?P<fy>\d{4})?\s*(?P<fp>Q[1-4]|FY)?\s*:\s*"
    r"(?P<value>[-+]?\d+(?:\.\d+)?)\s+filed\s+(?P<filed>\d{4}-\d{2}-\d{2})"
    r"(?:\s+form\s+(?P<form>[A-Za-z0-9/-]+))?"
    r"(?:\s+frame\s+(?P<frame>[A-Za-z0-9]+))?",
    re.IGNORECASE,
)

_SEC_FACT_PERIOD_RE = re.compile(
    r"(?P<concept>[A-Za-z][A-Za-z0-9]+)\s+\((?P<unit>[^)]+)\)\s+"
    r"for\s+(?P<period_kind>fiscal quarter|fiscal year)\s+ending\s+"
    r"(?P<end>\d{4}-\d{2}-\d{2}):\s*"
    r"(?P<value>[-+]?\d+(?:\.\d+)?)\s+\(form\s+(?P<form>[A-Za-z0-9/-]+)\)",
    re.IGNORECASE,
)

_SERIES_OBS_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2}):\s*(?P<value>[-+]?\d+(?:\.\d+)?)")


def canonicalize_search_results(
    results: Iterable[SearchResult],
    ticker: str,
    entity_resolution: EntityResolution | None = None,
) -> list[CanonicalFact]:
    """Convert structured provider snippets into replayable canonical facts."""
    result_list = list(results)
    entity = entity_resolution or resolve_entity(ticker, search_results=result_list)
    facts: list[CanonicalFact] = []
    for result in result_list:
        provider = str(result.raw.get("provider", "")).lower()
        if provider == "sec_company_facts":
            facts.extend(_sec_company_fact_rows(result, ticker, entity))
        elif provider == "fred":
            facts.extend(_fred_rows(result, ticker, entity))
        elif result.raw.get("provider"):
            facts.extend(_generic_structured_row(result, ticker, entity))
    return _dedupe_facts(facts)


def canonicalize_evidence(
    evidence: Iterable[Evidence],
    ticker: str,
    entity_resolution: EntityResolution | None = None,
) -> list[CanonicalFact]:
    """Fallback canonicalization when only normalized evidence is available."""
    evidence_list = list(evidence)
    entity = entity_resolution or resolve_entity(ticker, evidence=evidence_list)
    facts: list[CanonicalFact] = []
    for item in evidence_list:
        if not item.is_official_primary:
            continue
        source = assess_source(item.url, item.title)
        sec_rows = _sec_company_fact_rows_from_text(
            text=item.text,
            url=item.url,
            title=item.title,
            ticker=ticker,
            entity=entity,
            filed=item.published_at,
        )
        if sec_rows:
            facts.extend(sec_rows)
            continue
        if _looks_like_sec_company_facts(item):
            continue
        number = extract_numbers(item.text)[:1]
        facts.append(
            CanonicalFact(
                fact_id=_fact_id(item.url, item.title, item.published_at or "", number[0] if number else ""),
                source_type=item.source_type,
                authority_tier=item.source_tier,
                license_tag=item.license_tag,
                entity_id=entity.entity_id,
                ticker=ticker.upper(),
                cik=entity.cik,
                lei=entity.lei,
                filing_date=item.published_at,
                observation_date=item.published_at,
                fact_name=item.title,
                value=number[0] if number else None,
                provenance_locator=item.url,
                parser_confidence=0.55 if number else 0.35,
                raw={"domain": source.domain},
            )
        )
    return _dedupe_facts(facts)


def _sec_company_fact_rows(result: SearchResult, ticker: str, entity: EntityResolution) -> list[CanonicalFact]:
    rows = []
    source = assess_source(result.url, result.title)
    for match in _SEC_FACT_RE.finditer(result.snippet):
        period = " ".join(part for part in [match.group("fy"), match.group("fp"), match.group("frame")] if part)
        unit = match.group("unit")
        rows.append(
            CanonicalFact(
                fact_id=_fact_id(result.url, match.group("concept"), period, match.group("filed"), match.group("value")),
                source_type=source.source_type,
                authority_tier=source.source_tier,
                license_tag=source.license_tag,
                entity_id=entity.entity_id,
                ticker=ticker.upper(),
                cik=entity.cik,
                lei=entity.lei,
                report_period=period or None,
                filing_date=match.group("filed"),
                observation_date=period or None,
                unit=unit,
                currency="USD" if unit == "USD" else None,
                fact_name=match.group("concept"),
                value=_coerce_number(match.group("value")),
                provenance_locator=result.url,
                parser_confidence=0.90,
                raw={"form": match.group("form"), "frame": match.group("frame"), "provider": result.raw.get("provider")},
            )
        )
    rows.extend(
        _sec_company_fact_rows_from_text(
            text=result.snippet,
            url=result.url,
            title=result.title,
            ticker=ticker,
            entity=entity,
            filed=result.published_at,
        )
    )
    return rows


def _sec_company_fact_rows_from_text(
    text: str,
    url: str,
    title: str,
    ticker: str,
    entity: EntityResolution,
    filed: str | None,
) -> list[CanonicalFact]:
    rows = []
    source = assess_source(url, title)
    for match in _SEC_FACT_PERIOD_RE.finditer(text):
        end = match.group("end")
        unit = match.group("unit")
        rows.append(
            CanonicalFact(
                fact_id=_fact_id(url, match.group("concept"), end, filed or "", match.group("value")),
                source_type=source.source_type,
                authority_tier=source.source_tier,
                license_tag=source.license_tag,
                entity_id=entity.entity_id,
                ticker=ticker.upper(),
                cik=entity.cik,
                lei=entity.lei,
                report_period=end,
                filing_date=filed,
                observation_date=end,
                unit=unit,
                currency="USD" if unit == "USD" else None,
                fact_name=match.group("concept"),
                value=_coerce_number(match.group("value")),
                provenance_locator=url,
                parser_confidence=0.88,
                raw={
                    "form": match.group("form"),
                    "period_kind": match.group("period_kind").lower(),
                    "provider": "sec_company_facts",
                },
            )
        )
    return rows


def _looks_like_sec_company_facts(item: Evidence) -> bool:
    return "companyfacts" in item.url.lower() or item.title.lower().startswith("sec company facts")


def _fred_rows(result: SearchResult, ticker: str, entity: EntityResolution) -> list[CanonicalFact]:
    rows = []
    source = assess_source(result.url, result.title)
    series_id = result.raw.get("series_id")
    observations = result.raw.get("observations")
    if isinstance(observations, list):
        for obs in observations:
            if not isinstance(obs, dict) or obs.get("value") in {None, "."}:
                continue
            observation_date = str(obs.get("date", ""))
            value = str(obs.get("value", ""))
            rows.append(
                CanonicalFact(
                    fact_id=_fact_id(result.url, str(series_id), observation_date, value),
                    source_type=source.source_type,
                    authority_tier=source.source_tier,
                    license_tag=source.license_tag,
                    entity_id=entity.entity_id,
                    ticker=ticker.upper(),
                    observation_date=observation_date,
                    vintage_date=obs.get("realtime_start") or result.published_at,
                    fact_name=str(series_id or result.title),
                    value=_coerce_number(value),
                    provenance_locator=result.url,
                    parser_confidence=0.88,
                    raw={
                        "provider": "fred",
                        "series_id": series_id,
                        "realtime_start": obs.get("realtime_start"),
                        "realtime_end": obs.get("realtime_end"),
                    },
                )
            )
        if rows:
            return rows
    for match in _SERIES_OBS_RE.finditer(result.snippet):
        rows.append(
            CanonicalFact(
                fact_id=_fact_id(result.url, str(series_id), match.group("date"), match.group("value")),
                source_type=source.source_type,
                authority_tier=source.source_tier,
                license_tag=source.license_tag,
                entity_id=entity.entity_id,
                ticker=ticker.upper(),
                observation_date=match.group("date"),
                vintage_date=result.published_at,
                fact_name=str(series_id or result.title),
                value=_coerce_number(match.group("value")),
                provenance_locator=result.url,
                parser_confidence=0.82,
                raw={"provider": "fred", "series_id": series_id},
            )
        )
    return rows


def _generic_structured_row(result: SearchResult, ticker: str, entity: EntityResolution) -> list[CanonicalFact]:
    source = assess_source(result.url, result.title)
    provider = result.raw.get("provider")
    rows = result.raw.get("rows")
    if isinstance(rows, list):
        facts = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if value in {None, "", "."}:
                continue
            observation_date = str(
                row.get("date")
                or row.get("period")
                or row.get("TimePeriod")
                or row.get("year")
                or result.published_at
                or ""
            )
            fact_name = str(
                result.raw.get("series_id")
                or result.raw.get("indicator")
                or result.raw.get("table_name")
                or result.raw.get("series_code")
                or result.raw.get("key")
                or result.title
            )
            facts.append(
                CanonicalFact(
                    fact_id=_fact_id(result.url, str(provider), fact_name, observation_date, str(value)),
                    source_type=source.source_type,
                    authority_tier=source.source_tier,
                    license_tag=source.license_tag,
                    entity_id=entity.entity_id,
                    ticker=ticker.upper(),
                    filing_date=result.published_at,
                    observation_date=observation_date or result.published_at,
                    unit=row.get("unit") or row.get("units"),
                    fact_name=fact_name,
                    value=_coerce_number(str(value)),
                    provenance_locator=result.url,
                    parser_confidence=0.82,
                    raw={
                        "provider": provider,
                        "row": row,
                        "series_id": result.raw.get("series_id"),
                        "indicator": result.raw.get("indicator"),
                        "table_name": result.raw.get("table_name"),
                        "series_code": result.raw.get("series_code"),
                        "key": result.raw.get("key"),
                    },
                )
            )
        if facts:
            return facts
    numbers = extract_numbers(result.snippet)
    return [
        CanonicalFact(
            fact_id=_fact_id(result.url, result.title, result.published_at or "", ",".join(numbers[:3])),
            source_type=source.source_type,
            authority_tier=source.source_tier,
            license_tag=source.license_tag,
            entity_id=entity.entity_id,
            ticker=ticker.upper(),
            cik=entity.cik,
            lei=entity.lei,
            filing_date=result.published_at,
            observation_date=result.published_at,
            fact_name=result.title,
            value=numbers[0] if numbers else None,
            provenance_locator=result.url,
            parser_confidence=0.50 if numbers else 0.30,
            raw={"provider": provider},
        )
    ]


def _fact_id(*parts: str) -> str:
    payload = "|".join(str(part) for part in parts)
    return "fact_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _coerce_number(value: str) -> int | float | str:
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _dedupe_facts(facts: list[CanonicalFact]) -> list[CanonicalFact]:
    seen = set()
    deduped = []
    for fact in facts:
        if fact.fact_id in seen:
            continue
        seen.add(fact.fact_id)
        deduped.append(fact)
    return deduped
