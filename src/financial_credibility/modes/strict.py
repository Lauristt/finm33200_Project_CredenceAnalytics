"""Strict-mode helper that bypasses agentic query expansion."""

from __future__ import annotations

from typing import Any

from ..models import EvidencePack, SearchResult
from ..toolkit import FinancialCredibilityToolkit


def run_strict(
    toolkit: FinancialCredibilityToolkit,
    claim: str,
    ticker: str,
    as_of_date: str | None = None,
    max_sources: int = 8,
    prefetched_results: list[dict[str, Any] | SearchResult] | None = None,
) -> EvidencePack:
    """Run the core toolkit pipeline with `mode='strict'` metadata."""
    return toolkit.build_evidence_pack(
        claim=claim,
        ticker=ticker,
        as_of_date=as_of_date,
        max_sources=max_sources,
        prefetched_results=prefetched_results,
        mode="strict",
    )
