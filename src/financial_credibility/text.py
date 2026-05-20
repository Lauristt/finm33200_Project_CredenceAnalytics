"""Text utility functions used by retrieval scoring and heuristic judging."""

from __future__ import annotations

import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}


def tokenize(text: str) -> set[str]:
    """Tokenize text into a small stopword-filtered set."""
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\.]*", text.lower())
        if token not in STOPWORDS and len(token) > 1
    }


def token_overlap(a: str, b: str) -> float:
    """Return the fraction of tokens from `a` that also appear in `b`."""
    a_tokens = tokenize(a)
    b_tokens = tokenize(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens)
