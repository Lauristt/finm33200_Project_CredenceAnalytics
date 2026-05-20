"""Agentic-mode wrapper.

This mode expands the search plan but still uses the same deterministic
retrieval, extraction, judging, and verification pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..argument import classify_argument_type
from ..models import EvidencePack, SearchResult
from ..search import build_queries
from ..toolkit import FinancialCredibilityToolkit


@dataclass
class AgenticCredibilityRunner:
    """Exploratory wrapper over the same retrieval/evidence/scoring system."""

    toolkit: FinancialCredibilityToolkit

    def run(
        self,
        claim: str,
        ticker: str,
        as_of_date: str | None = None,
        max_sources: int = 8,
        prefetched_results: list[dict[str, Any] | SearchResult] | None = None,
    ) -> EvidencePack:
        """Run the toolkit with an expanded search plan and annotated metadata."""
        classification = classify_argument_type(claim)
        plan = self._make_search_plan(claim, ticker, classification.argument_type)
        pack = self.toolkit.build_evidence_pack(
            claim=claim,
            ticker=ticker,
            as_of_date=as_of_date,
            max_sources=max_sources,
            prefetched_results=prefetched_results,
            mode="agentic",
            extra_queries=plan,
        )
        metadata = dict(pack.metadata)
        metadata["agentic_search_plan"] = plan
        return EvidencePack(
            claim=pack.claim,
            ticker=pack.ticker,
            as_of_date=pack.as_of_date,
            argument_type=pack.argument_type,
            classification_confidence=pack.classification_confidence,
            verdict=pack.verdict,
            credibility_label=pack.credibility_label,
            credibility_score=pack.credibility_score,
            score_breakdown=pack.score_breakdown,
            numeric_check=pack.numeric_check,
            logic_check=pack.logic_check,
            source_check=pack.source_check,
            overall_conclusion=pack.overall_conclusion,
            evidence=pack.evidence,
            risk_flags=pack.risk_flags,
            mode="agentic",
            metadata=metadata,
        )

    def _make_search_plan(self, claim: str, ticker: str, argument_type) -> list[str]:
        """Create normal plus counter-evidence-oriented queries."""
        base_queries = build_queries(claim, ticker, argument_type)
        counter_queries = [
            f"{ticker} {claim} correction restatement contradiction",
            f"{ticker} {claim} SEC filing official source",
        ]
        return base_queries + counter_queries
