"""Lightweight claim-intent helpers shared by routing and verification."""

from __future__ import annotations

import re


_CORPORATE_TRANSACTION_PATTERNS = (
    r"\bacquir(?:e|es|ed|ing)\b",
    r"\bacquisition\b",
    r"\bmerg(?:e|es|ed|ing|er)\b",
    r"\btakeover\b",
    r"\bbuyout\b",
    r"\bpurchas(?:e|es|ed|ing)\b.*\b(?:company|stake|shares?|business|unit)\b",
    r"\bbought\b.*\b(?:company|stake|shares?|business|unit)\b",
    r"\b(?:minority|majority|equity)\s+stake\b",
    r"收购",
    r"并购",
    r"兼并",
    r"合并",
    r"入股",
    r"持股",
)


def is_corporate_transaction_claim(text: str) -> bool:
    """Return True for M&A/stake claims that need event evidence, not XBRL facts."""
    value = str(text or "").lower()
    return any(re.search(pattern, value) for pattern in _CORPORATE_TRANSACTION_PATTERNS)
