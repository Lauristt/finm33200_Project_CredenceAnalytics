"""Time-context inference for claim retrieval windows."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class TimeContext:
    """Resolved date context used to anchor retrieval."""

    effective_as_of_date: str | None
    user_as_of_date: str | None
    event_date: str | None
    publication_date: str | None
    source: str
    confidence: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def infer_time_context(
    text: str,
    as_of_date: str | None = None,
    anchor_date: str | date | None = None,
) -> TimeContext:
    """Infer the date that retrieval should be anchored to.

    The returned date is intentionally conservative: an explicit caller-provided
    as-of date wins, otherwise objective dates in the document are used before
    falling back to publication date or today's date at the orchestration layer.
    """
    user_as_of = _parse_iso_date(as_of_date)
    anchor = _parse_date_like(anchor_date)
    default_year = (user_as_of or anchor or date.today()).year
    dated_mentions = _find_dated_mentions(text, default_year=default_year)
    publication = next((item for item in dated_mentions if item["kind"] == "publication"), None)
    event = next((item for item in dated_mentions if item["kind"] == "event"), None)
    publication_date = publication["date"] if publication else None
    event_date = event["date"] if event else None
    notes: list[str] = []
    if dated_mentions:
        notes.append("absolute_date_detected")
    if publication_date:
        notes.append("publication_date_detected")

    if user_as_of:
        return TimeContext(
            effective_as_of_date=user_as_of.isoformat(),
            user_as_of_date=user_as_of.isoformat(),
            event_date=event_date.isoformat() if event_date else None,
            publication_date=publication_date.isoformat() if publication_date else None,
            source="user_as_of_date",
            confidence=1.0,
            notes=notes,
        )

    if event_date:
        return TimeContext(
            effective_as_of_date=event_date.isoformat(),
            user_as_of_date=None,
            event_date=event_date.isoformat(),
            publication_date=publication_date.isoformat() if publication_date else None,
            source="explicit_event_date",
            confidence=0.95,
            notes=notes,
        )

    relative_anchor = publication_date or anchor
    relative_event = _relative_date_from_text(text, relative_anchor)
    if relative_event:
        notes.append("relative_date_detected")
        return TimeContext(
            effective_as_of_date=relative_event.isoformat(),
            user_as_of_date=None,
            event_date=relative_event.isoformat(),
            publication_date=publication_date.isoformat() if publication_date else None,
            source="relative_context_date",
            confidence=0.80,
            notes=notes,
        )

    if publication_date:
        return TimeContext(
            effective_as_of_date=publication_date.isoformat(),
            user_as_of_date=None,
            event_date=None,
            publication_date=publication_date.isoformat(),
            source="publication_date",
            confidence=0.70,
            notes=notes,
        )

    if anchor:
        return TimeContext(
            effective_as_of_date=anchor.isoformat(),
            user_as_of_date=None,
            event_date=None,
            publication_date=None,
            source="anchor_date",
            confidence=0.55,
            notes=notes,
        )

    return TimeContext(
        effective_as_of_date=None,
        user_as_of_date=None,
        event_date=None,
        publication_date=None,
        source="unresolved",
        confidence=0.0,
        notes=notes or ["no_date_context_detected"],
    )


def _parse_date_like(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    return _parse_iso_date(value)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _find_dated_mentions(text: str, default_year: int | None = None) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for match in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            mentions.append(_mention(parsed, match.span(), text))
    for match in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text):
        year = _normalize_year(int(match.group(3)))
        parsed = _safe_date(year, int(match.group(1)), int(match.group(2)))
        if parsed:
            mentions.append(_mention(parsed, match.span(), text))
    month_pattern = "|".join(sorted(_MONTHS, key=len, reverse=True))
    for match in re.finditer(rf"\b({month_pattern})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", text, re.IGNORECASE):
        parsed = _safe_date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
        if parsed:
            mentions.append(_mention(parsed, match.span(), text))
    for match in re.finditer(rf"\b(\d{{1,2}})\s+({month_pattern})\.?\s+(\d{{4}})\b", text, re.IGNORECASE):
        parsed = _safe_date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))
        if parsed:
            mentions.append(_mention(parsed, match.span(), text))
    if default_year:
        for match in re.finditer(rf"\b({month_pattern})\.?\s+(\d{{1,2}})(?!,?\s*\d{{4}})\b", text, re.IGNORECASE):
            parsed = _safe_date(default_year, _MONTHS[match.group(1).lower()], int(match.group(2)))
            if parsed:
                mentions.append(_mention(parsed, match.span(), text))
        for match in re.finditer(rf"\b(\d{{1,2}})\s+({month_pattern})\.?(?!\s+\d{{4}})\b", text, re.IGNORECASE):
            parsed = _safe_date(default_year, _MONTHS[match.group(2).lower()], int(match.group(1)))
            if parsed:
                mentions.append(_mention(parsed, match.span(), text))
    mentions.sort(key=lambda item: item["span"][0])
    deduped = []
    seen = set()
    for item in mentions:
        key = (item["date"], item["span"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _mention(value: date, span: tuple[int, int], text: str) -> dict[str, Any]:
    before = text[max(0, span[0] - 32) : span[0]].lower()
    is_publication = bool(re.search(r"\b(published|updated|posted|dateline)\b", before))
    return {"date": value, "span": span, "kind": "publication" if is_publication else "event"}


def _relative_date_from_text(text: str, anchor: date | None) -> date | None:
    if not anchor:
        return None
    lower = text.lower()
    if re.search(r"\byesterday\b", lower):
        return anchor - timedelta(days=1)
    if re.search(r"\btoday\b", lower):
        return anchor
    weekday_mentions = [
        (match.start(), weekday, target)
        for weekday, target in _WEEKDAYS.items()
        for match in re.finditer(rf"\b{weekday}\b", lower)
    ]
    if weekday_mentions:
        _position, _weekday, target = min(weekday_mentions, key=lambda item: item[0])
        delta = (anchor.weekday() - target) % 7
        return anchor - timedelta(days=delta)
    return None


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year if year < 70 else 1900 + year
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
