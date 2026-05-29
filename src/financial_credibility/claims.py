"""Atomic claim decomposition for claim-level financial verification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .argument import classify_argument_type
from .models import AtomicClaim


_CLAUSE_SPLIT_RE = re.compile(r"(?:[;\n。；]+|(?<=[.!?])\s+)")
_SOFT_AND_RE = re.compile(r"\s+(?:and|while|whereas|but)\s+", re.IGNORECASE)
_MARKET_COMMA_SPLIT_RE = re.compile(
    r",\s+(?=(?:the\s+)?(?:Dow Jones|Dow|Nasdaq|Russell|S&P\s*500)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ClaimPiece:
    text: str
    context_window: str
    context_window_source: str


def decompose_claims(claim: str) -> list[AtomicClaim]:
    """Split a user statement into stable, individually verifiable claims.

    Objective, falsifiable asset properties can be fact-checked. Investor
    reassurance, discussion/talk framing, and future business capability remain
    classified as non-factual atoms rather than retrieval targets.
    """
    pieces: list[_ClaimPiece] = []
    active_context: str | None = None
    ambient_context: list[str] = []
    for sentence in _CLAUSE_SPLIT_RE.split(claim):
        cleaned = _clean_claim_piece(sentence)
        if not cleaned:
            continue
        if _is_context_only_sentence(cleaned):
            inline_context = _inline_context_marker(cleaned)
            if inline_context:
                active_context = inline_context
            ambient_context = _append_context_sentence(ambient_context, cleaned)
            continue
        context = _context_heading(cleaned)
        if context:
            active_context = context
            ambient_context = _append_context_sentence(ambient_context, cleaned)
            continue
        sentence_has_financial_piece = False
        metric_context: str | None = None
        for part in _split_compound_clause(cleaned):
            sentence_has_financial_piece = sentence_has_financial_piece or _looks_financial_claim(part)
            part_metric_context = _financial_metric_context(part)
            if _is_bare_metric_change(part) and metric_context:
                part = f"{metric_context} {part}"
                part_metric_context = _financial_metric_context(part)
            inline_context = _inline_context_marker(part)
            context_source = "claim"
            if inline_context and _looks_financial_claim(part):
                active_context = inline_context
                piece_text = part
                context_source = "inline_context"
            elif active_context and _looks_financial_claim(part) and not _has_context_marker(part, active_context):
                piece_text = f"{active_context}, {part}"
                context_source = "section_context"
            else:
                piece_text = part
            pieces.append(
                _ClaimPiece(
                    text=piece_text,
                    context_window=_context_window(ambient_context, active_context, cleaned, part, piece_text),
                    context_window_source=context_source if context_source != "claim" else _context_window_source(ambient_context, active_context, cleaned, part),
                )
            )
            if part_metric_context:
                metric_context = part_metric_context
        if _looks_contextual_sentence(cleaned) and not sentence_has_financial_piece:
            ambient_context = _append_context_sentence(ambient_context, cleaned)

    if not pieces:
        cleaned = _clean_claim_piece(claim)
        pieces = [_ClaimPiece(cleaned, cleaned, "claim")]

    atoms = []
    for index, piece in enumerate(_dedupe_pieces_preserving_order(pieces), start=1):
        classification = classify_argument_type(piece.text)
        atoms.append(
            AtomicClaim(
                claim_id=f"claim_{index}",
                text=piece.text,
                argument_type=classification.argument_type,
                classification_confidence=classification.confidence,
                signals=classification.signals,
                context_window=piece.context_window,
                context_window_source=piece.context_window_source,
            )
        )
    return atoms


def _split_compound_clause(text: str) -> list[str]:
    parts = []
    for part in _SOFT_AND_RE.split(text):
        parts.extend(_split_market_comma_clause(part))
    parts = [_clean_claim_piece(part) for part in parts]
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return [text]
    if all(_looks_financial_claim(part) for part in parts):
        return parts
    return [text]


def _split_market_comma_clause(text: str) -> list[str]:
    if not _MARKET_COMMA_SPLIT_RE.search(text):
        return [text]
    parts = _MARKET_COMMA_SPLIT_RE.split(text)
    if all(_looks_market_move(part) for part in parts if part.strip()):
        return parts
    return [text]


def _looks_market_move(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(r"\b(s&p\s*500|dow|nasdaq|russell)\b", lower)
        and re.search(r"\b(rose|fell|added|climbed|gained|slipped|dropped|rallied|advanced|up|down)\b|%", lower)
    )


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


def _looks_contextual_sentence(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(r"\b(published|updated|posted|dateline|reuters|ap news|marketwatch|bloomberg)\b", lower)
        or re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|yesterday)\b", lower)
        or re.search(r"\b(for the year|year to date|ytd|this year)\b", lower)
        or re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b", lower)
    )


def _is_context_only_sentence(text: str) -> bool:
    lower = text.lower().strip()
    if re.search(r"\b(published|updated|posted|dateline)\b", lower):
        return True
    if re.match(r"^how\b", lower) and re.search(r"\b(fared|performed|moved)\b", lower):
        return True
    if re.match(r"^(?:reuters|ap news|bloomberg|marketwatch)\b", lower) and not re.search(
        r"\b(reported|rose|fell|added|climbed|revenue|income|eps|sales)\b",
        lower,
    ):
        return True
    return False


def _financial_metric_context(text: str) -> str | None:
    lower = text.lower()
    contexts = [
        ("non-GAAP diluted EPS", r"\bnon[- ]gaap\s+diluted\s+eps\b"),
        ("GAAP diluted EPS", r"\bgaap\s+diluted\s+eps\b"),
        ("earnings per share", r"\b(?:eps|earnings per share)\b"),
        ("free cash flow", r"\bfree cash flow\b"),
        ("operating income", r"\boperating income\b"),
        ("net income", r"\bnet income\b"),
        ("revenue", r"\b(?:revenue|net sales|sales)\b"),
    ]
    for label, pattern in contexts:
        if re.search(pattern, lower):
            return label
    return None


def _is_bare_metric_change(text: str) -> bool:
    return bool(
        re.match(r"^(?:up|down|higher|lower|increased|decreased|rose|fell)\b", text.strip(), flags=re.IGNORECASE)
        and re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:%|percent\b)", text, flags=re.IGNORECASE)
        and not _financial_metric_context(text)
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


def _context_window(
    ambient_context: list[str],
    active_context: str | None,
    sentence: str,
    part: str,
    piece_text: str,
) -> str:
    values = list(ambient_context)
    if active_context and not _has_context_marker(sentence, active_context):
        values.append(active_context)
    if sentence and sentence.lower() != part.lower():
        values.append(sentence)
    values.append(piece_text)
    return " ".join(_dedupe_preserving_order([_clean_claim_piece(value) for value in values if value]))


def _context_window_source(
    ambient_context: list[str],
    active_context: str | None,
    sentence: str,
    part: str,
) -> str:
    if active_context and not _has_context_marker(sentence, active_context):
        return "section_context"
    if ambient_context:
        return "surrounding_context"
    if sentence and sentence.lower() != part.lower():
        return "sentence_context"
    return "claim"


def _append_context_sentence(values: list[str], sentence: str, max_items: int = 2) -> list[str]:
    if not sentence:
        return values
    updated = _dedupe_preserving_order([*values, sentence])
    return updated[-max_items:]


def _dedupe_pieces_preserving_order(values: list[_ClaimPiece]) -> list[_ClaimPiece]:
    seen: set[str] = set()
    deduped = []
    for value in values:
        key = value.text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


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
