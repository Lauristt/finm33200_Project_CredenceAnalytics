"""Input cleaning for copied financial articles, notes, and statements."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any


_BOILERPLATE_RE = re.compile(
    r"^(?:"
    r"advertisement|advertising|sponsored|sponsored content|paid post|"
    r"subscribe|sign up|sign in|log in|create account|"
    r"share|copy link|listen to article|read more|related articles?|"
    r"skip to main content|menu|search|home|markets|newsletter|"
    r"cookies?|privacy policy|terms of use|all rights reserved|"
    r"download app|follow us|open navigation|close navigation"
    r")\b",
    re.IGNORECASE,
)
_SPONSOR_BLOCK_RE = re.compile(
    r"\b(?:paid for by|sponsored by|sponsored content|advertisement from|promoted by)\b",
    re.IGNORECASE,
)
_LOGO_RE = re.compile(r"\blogo\b$", re.IGNORECASE)
_URL_ONLY_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
_DATE_LINE_RE = re.compile(
    r"\b(?:published|updated|filed|reported|released)\b|\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)
_FINANCIAL_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"revenue|sales|income|earnings|eps|cash flow|assets|liabilities|debt|margin|"
    r"stock|shares?|index|nasdaq|dow|s&p|russell|treasury|yield|bond|credit|"
    r"oil|gold|dollar|euro|yen|inflation|cpi|ppi|pce|gdp|payrolls?|"
    r"rate|fed|bank|quarter|fiscal|year|ytd|market|price|volume|"
    r"rose|fell|added|slipped|gained|declined|increased|decreased|up|down"
    r")\b",
    re.IGNORECASE,
)
_TABLE_SIGNAL_RE = re.compile(r"(?:\$\s*)?-?\d[\d,]*(?:\.\d+)?%?|\b(?:q[1-4]|fy|ytd)\b", re.IGNORECASE)
_NOISE_CHARS_RE = re.compile(r"^[\W_]+$")


@dataclass(frozen=True)
class PreprocessedStatement:
    """A cleaned statement plus enough audit metadata to inspect the deletion."""

    original_text: str
    clean_text: str
    removed_lines: list[str] = field(default_factory=list)
    kept_line_count: int = 0
    original_line_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.clean_text.strip() != self.original_text.strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "original_length": len(self.original_text),
            "cleaned_length": len(self.clean_text),
            "original_line_count": self.original_line_count,
            "kept_line_count": self.kept_line_count,
            "removed_line_count": len(self.removed_lines),
            "removed_examples": self.removed_lines[:12],
            "notes": list(self.notes),
            "cleaned_statement": self.clean_text,
        }


def preprocess_statement(text: str) -> PreprocessedStatement:
    """Remove copied-webpage noise before entity extraction and claim checking."""
    original = str(text or "")
    normalized = _normalize_text(original)
    raw_lines = normalized.splitlines() or [normalized]
    kept: list[str] = []
    removed: list[str] = []
    seen: set[str] = set()
    sponsor_block = False

    for raw_line in raw_lines:
        line = _clean_line(raw_line)
        if not line:
            sponsor_block = False
            continue

        if sponsor_block:
            if _looks_like_article_resume(line):
                sponsor_block = False
            else:
                _remember_removed(removed, line)
                continue

        if _SPONSOR_BLOCK_RE.search(line):
            sponsor_block = True
            _remember_removed(removed, line)
            continue

        if _is_boilerplate_line(line):
            _remember_removed(removed, line)
            continue

        key = line.lower()
        if key in seen:
            _remember_removed(removed, line)
            continue
        seen.add(key)
        kept.append(line)

    clean = _format_clean_statement(kept)
    notes: list[str] = []
    if removed:
        notes.append("removed_webpage_boilerplate")
    if len(clean) < 80 and len(normalized) >= 160:
        notes.append("preprocessing_reverted_low_signal")
        return PreprocessedStatement(
            original_text=original,
            clean_text=_format_clean_statement([_clean_line(line) for line in raw_lines if _clean_line(line)]),
            removed_lines=[],
            kept_line_count=len([line for line in raw_lines if _clean_line(line)]),
            original_line_count=len(raw_lines),
            notes=notes,
        )
    if not clean:
        notes.append("preprocessing_empty_input")
        clean = normalized.strip()
    return PreprocessedStatement(
        original_text=original,
        clean_text=clean,
        removed_lines=removed,
        kept_line_count=len(kept),
        original_line_count=len(raw_lines),
        notes=notes,
    )


def _normalize_text(text: str) -> str:
    value = html.unescape(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _clean_line(line: str) -> str:
    value = line.strip(" \t")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_boilerplate_line(line: str) -> bool:
    lower = line.lower().strip()
    if not lower:
        return True
    if _URL_ONLY_RE.match(line) or _NOISE_CHARS_RE.match(line):
        return True
    if _LOGO_RE.search(line):
        return True
    if _BOILERPLATE_RE.match(line):
        return True
    if lower in {"facebook", "x", "linkedin", "email", "print", "comments", "gift article"}:
        return True
    if len(line) <= 3 and not re.search(r"\d", line):
        return True
    if _looks_like_market_or_statement_line(line):
        return False
    if len(line) <= 34 and re.search(r"\b(?:ad|sponsored|newsletter|cookie|subscribe|menu)\b", lower):
        return True
    return False


def _looks_like_market_or_statement_line(line: str) -> bool:
    return bool(_FINANCIAL_SIGNAL_RE.search(line) or _TABLE_SIGNAL_RE.search(line) or _DATE_LINE_RE.search(line))


def _looks_like_article_resume(line: str) -> bool:
    if _BOILERPLATE_RE.match(line) or _LOGO_RE.search(line):
        return False
    return _looks_like_market_or_statement_line(line) and len(line) >= 25


def _format_clean_statement(lines: list[str]) -> str:
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if buffer:
            paragraphs.append(" ".join(buffer).strip())
            buffer = []

    for line in lines:
        if not line:
            flush()
            continue
        if _is_standalone_heading(line):
            flush()
            paragraphs.append(line)
            continue
        if _is_table_like_line(line):
            flush()
            paragraphs.append(line)
            continue
        buffer.append(line)
        if re.search(r"[.!?]$|:$", line):
            flush()
    flush()
    return "\n\n".join(part for part in paragraphs if part).strip()


def _is_standalone_heading(line: str) -> bool:
    lower = line.lower().strip()
    if lower in {"on monday:", "on tuesday:", "on wednesday:", "on thursday:", "on friday:", "for the year:"}:
        return True
    if line.endswith(":") and len(line) <= 80:
        return True
    return len(line) <= 90 and not re.search(r"[.!?]$", line) and bool(_DATE_LINE_RE.search(line))


def _is_table_like_line(line: str) -> bool:
    if "\t" in line:
        return True
    if re.search(r"\s{2,}", line):
        return True
    return bool(_TABLE_SIGNAL_RE.search(line) and not re.search(r"[.!?]$", line) and len(line) <= 120)


def _remember_removed(removed: list[str], line: str) -> None:
    if len(removed) >= 50:
        return
    removed.append(line[:180])
