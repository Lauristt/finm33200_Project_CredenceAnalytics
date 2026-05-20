from __future__ import annotations

from itertools import combinations
from typing import Any

from .aggregation import aggregate_scores
from .argument import classify_argument_type
from .config import ToolkitConfig
from .extraction import EvidenceExtractor
from .judges import SemanticJudge, create_judge
from .models import EvidencePack, SearchResult, today_iso
from .search import SearchClient
from .verification import (
    build_overall_conclusion,
    verify_logic_claim,
    verify_numeric_claim,
    verify_sources,
)


class FinancialCredibilityToolkit:
    def __init__(
        self,
        config: ToolkitConfig | None = None,
        judge: SemanticJudge | None = None,
    ):
        self.config = config or ToolkitConfig.from_env()
        self.judge = judge or create_judge(self.config)

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "FinancialCredibilityToolkit":
        return cls(ToolkitConfig.from_env(env_file))

    def build_evidence_pack(
        self,
        claim: str,
        ticker: str,
        as_of_date: str | None = None,
        max_sources: int = 8,
        prefetched_results: list[dict[str, Any] | SearchResult] | None = None,
        mode: str = "agentic",
        extra_queries: list[str] | None = None,
    ) -> EvidencePack:
        as_of = as_of_date or today_iso()
        classification = classify_argument_type(claim)
        risk_flags: list[str] = []

        search_client = SearchClient(self.config, extra_queries=extra_queries or [])
        results, search_notes = search_client.search_financial_sources(
            claim=claim,
            ticker=ticker,
            argument_type=classification.argument_type,
            max_sources=max_sources,
            prefetched_results=prefetched_results,
        )
        if not results:
            risk_flags.append("search_unavailable")

        extractor = EvidenceExtractor(self.config)
        evidence, extraction_notes = extractor.extract(
            claim=claim,
            ticker=ticker,
            search_results=results,
            as_of_date=as_of,
            max_sources=max_sources,
        )

        self._judge_evidence(claim, classification.argument_type, evidence)
        self._score_independence(evidence)

        breakdown, verdict, label, final_flags = aggregate_scores(
            classification.argument_type,
            evidence,
            risk_flags,
        )
        numeric_check = verify_numeric_claim(claim, evidence, self.judge)
        logic_check = verify_logic_claim(claim, evidence, classification.argument_type, self.judge)
        source_check = verify_sources(evidence, breakdown)
        overall_conclusion = build_overall_conclusion(
            classification.argument_type,
            numeric_check,
            logic_check,
            source_check,
        )

        return EvidencePack(
            claim=claim,
            ticker=ticker.upper(),
            as_of_date=as_of,
            argument_type=classification.argument_type,
            classification_confidence=classification.confidence,
            verdict=verdict,
            credibility_label=label,
            credibility_score=breakdown.final_score,
            score_breakdown=breakdown,
            numeric_check=numeric_check,
            logic_check=logic_check,
            source_check=source_check,
            overall_conclusion=overall_conclusion,
            evidence=evidence,
            risk_flags=final_flags,
            mode=mode,
            metadata={
                "classification_signals": classification.signals,
                "needs_decomposition": classification.needs_decomposition,
                "search_notes": search_notes,
                "extraction_notes": extraction_notes,
            },
        )

    def _judge_evidence(self, claim: str, argument_type, evidence: list) -> None:
        for item in evidence:
            label, support_score, support_notes = self.judge.judge_evidence_support(claim, item)
            reasoning_score, reasoning_notes = self.judge.judge_reasoning_quality(
                claim,
                item,
                argument_type,
            )
            item.support_label = label
            item.support_score = support_score
            item.reasoning_quality_score = reasoning_score
            item.notes.extend(support_notes + reasoning_notes)

    def _score_independence(self, evidence: list) -> None:
        if not evidence:
            return
        if len(evidence) == 1:
            evidence[0].independence_score = 0.35
            evidence[0].notes.append("single evidence source")
            return

        scores: dict[str, list[float]] = {item.url: [] for item in evidence}
        for first, second in combinations(evidence, 2):
            score, notes = self.judge.judge_independence(first, second)
            scores[first.url].append(score)
            scores[second.url].append(score)
            first.notes.extend(notes[:1])

        for item in evidence:
            item_scores = scores[item.url]
            item.independence_score = round(sum(item_scores) / len(item_scores), 3)
