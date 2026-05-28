"""Atomic claim decomposition for claim-level financial verification."""

from __future__ import annotations

import re

from .argument import classify_argument_type
from .models import AtomicClaim


_CLAUSE_SPLIT_RE = re.compile(r"(?:[;\n。；]+|(?<=[.!?])\s+)")
_SOFT_AND_RE = re.compile(r"\s+(?:and|while|whereas|but)\s+", re.IGNORECASE)


def decompose_claims(claim: str) -> list[AtomicClaim]:
    """Split a user statement into stable, individually verifiable claims.

    Objective, falsifiable asset properties can be fact-checked. Investor
    reassurance, discussion/talk framing, and future business capability remain
    classified as non-factual atoms rather than retrieval targets.
    """
    pieces: list[str] = []
    active_context: str | None = None
    for sentence in _CLAUSE_SPLIT_RE.split(claim):
        cleaned = _clean_claim_piece(sentence)
        if not cleaned:
            continue
        context = _context_heading(cleaned)
        if context:
            active_context = context
            continue
        for part in _split_compound_clause(cleaned):
            inline_context = _inline_context_marker(part)
            if inline_context and _looks_financial_claim(part):
                active_context = inline_context
                pieces.append(part)
            elif active_context and _looks_financial_claim(part) and not _has_context_marker(part, active_context):
                pieces.append(f"{active_context}, {part}")
            else:
                pieces.append(part)

    if not pieces:
        pieces = [_clean_claim_piece(claim)]

    atoms = []
    for index, piece in enumerate(_dedupe_preserving_order(pieces), start=1):
        classification = classify_argument_type(piece)
        atoms.append(
            AtomicClaim(
                claim_id=f"claim_{index}",
                text=piece,
                argument_type=classification.argument_type,
                classification_confidence=classification.confidence,
                signals=classification.signals,
            )
        )
    return atoms


def _split_compound_clause(text: str) -> list[str]:
    parts = [_clean_claim_piece(part) for part in _SOFT_AND_RE.split(text)]
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return [text]
    if all(_looks_financial_claim(part) for part in parts):
        return parts
    return [text]


def _looks_financial_claim(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(
            r"\b(revenue|sales|income|eps|cash flow|debt|leverage|margin|buyback|repurchase|"
            r"growth|grew|declined|increased|decreased|improved|higher|lower|rate|inflation|gdp)\b",
            lower,
        )
        or re.search(r"[-+]?\$?\d", lower)
    )


def _context_heading(text: str) -> str | None:
    lower = text.lower().strip()
    if re.fullmatch(r"(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)", lower):
        return text if lower.startswith("on ") else f"On {text}"
    if re.fullmatch(r"for the year|year to date|ytd|this year", lower):
        return "For the year"
    if re.fullmatch(r"today|yesterday", lower):
        return text.capitalize()
    return None


def _has_context_marker(text: str, context: str) -> bool:
    lower = text.lower()
    context_lower = context.lower()
    if context_lower in lower:
        return True
    if context_lower.startswith("on "):
        return context_lower[3:] in lower
    if context_lower == "for the year":
        return bool(re.search(r"\b(for the year|year to date|ytd|this year)\b", lower))
    return False


def _inline_context_marker(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\b(for the year|year to date|ytd|this year)\b", lower):
        return "For the year"
    weekday_matches = [
        (match.start(), match.group(0))
        for match in re.finditer(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
    ]
    if weekday_matches:
        _position, weekday = min(weekday_matches, key=lambda item: item[0])
        return f"On {weekday.capitalize()}"
    if re.search(r"\byesterday\b", lower):
        return "Yesterday"
    if re.search(r"\btoday\b", lower):
        return "Today"
    return None


def _clean_claim_piece(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" \t\r\n,.;:")).strip()


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped
