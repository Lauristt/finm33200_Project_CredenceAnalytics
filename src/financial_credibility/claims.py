"""Atomic claim decomposition for claim-level financial verification."""

from __future__ import annotations

import re

from .argument import classify_argument_type
from .models import AtomicClaim


_CLAUSE_SPLIT_RE = re.compile(r"(?:[;\n。；]+|(?<=[.!?])\s+)")
_SOFT_AND_RE = re.compile(r"\s+(?:and|while|whereas|but)\s+", re.IGNORECASE)


def decompose_claims(claim: str) -> list[AtomicClaim]:
    """Split a user statement into stable, individually verifiable claims."""
    pieces: list[str] = []
    for sentence in _CLAUSE_SPLIT_RE.split(claim):
        cleaned = _clean_claim_piece(sentence)
        if not cleaned:
            continue
        pieces.extend(_split_compound_clause(cleaned))

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
