"""Top-level orchestration API for the credibility toolkit.

This module owns the main pipeline boundary. Everything below this layer is a
smaller component: argument classification, retrieval, extraction, semantic
judging, aggregation, and explicit verification. Developers integrating the
package should usually start with `FinancialCredibilityToolkit`.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Callable

from .aggregation import aggregate_scores
from .argument import classify_argument_type
from .audit import build_audit_trace
from .claim_verification import verify_atomic_claims
from .claims import decompose_claims
from .config import ToolkitConfig
from .entity import resolve_entity
from .extraction import EvidenceExtractor
from .facts import canonicalize_evidence, canonicalize_search_results
from .judges import SemanticJudge, create_judge
from .models import EvidencePack, SearchResult, today_iso, to_plain
from .routing import route_sources
from .rubrics import FACTUAL_TYPES
from .search import SearchClient
from .source_selection import selected_provider_names_from_plan, select_sources_for_claims
from .verification import (
    build_overall_conclusion,
    verify_logic_claim,
    verify_numeric_claim,
    verify_sources,
)


class FinancialCredibilityToolkit:
    """Main programmatic entry point.

    A toolkit instance holds immutable configuration and one semantic judge.
    The judge may be local heuristic, OpenAI-backed, or Anthropic-backed
    depending on `ToolkitConfig`.
    """

    def __init__(
        self,
        config: ToolkitConfig | None = None,
        judge: SemanticJudge | None = None,
    ):
        self.config = config or ToolkitConfig.from_env()
        self.judge = judge or create_judge(self.config)

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "FinancialCredibilityToolkit":
        """Create a toolkit using `.env` or an explicitly provided env file."""
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
        trace_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> EvidencePack:
        """Build a complete credibility assessment for one equity claim.

        This is the function exposed through the CLI and tool schema adapters.
        It returns an `EvidencePack`, which includes both the legacy weighted
        score and the newer numeric/logic/source/overall confidence checks.

        `prefetched_results` is the best hook for tests or demos where network
        retrieval should be skipped.
        """
        as_of = as_of_date or today_iso()
        classification = classify_argument_type(claim)
        _emit_trace(
            trace_callback,
            "classify_claim",
            "ok",
            f"Classified claim as {classification.argument_type.value}.",
            outputs={
                "argument_type": classification.argument_type,
                "confidence": classification.confidence,
                "signals": classification.signals,
                "needs_decomposition": classification.needs_decomposition,
            },
        )
        risk_flags: list[str] = []
        planned_atomic_claims = decompose_claims(claim)
        fact_checkable_claims = [
            item for item in planned_atomic_claims if item.argument_type in FACTUAL_TYPES
        ]
        _emit_trace(
            trace_callback,
            "decompose_claims",
            "ok" if planned_atomic_claims else "empty",
            f"Prepared {len(fact_checkable_claims)} fact-checkable claim(s) and skipped {len(planned_atomic_claims) - len(fact_checkable_claims)} opinion/forecast claim(s).",
            outputs={
                "claims": [
                    {
                        "claim_id": item.claim_id,
                        "text": item.text,
                        "argument_type": item.argument_type,
                        "fact_checkable": item.argument_type in FACTUAL_TYPES,
                    }
                    for item in planned_atomic_claims
                ]
            },
        )
        _emit_trace(
            trace_callback,
            "select_sources",
            "running",
            "Selecting official-first data sources for atomic claims.",
        )
        source_selection_plan = select_sources_for_claims(fact_checkable_claims, self.config)
        selected_providers = selected_provider_names_from_plan(source_selection_plan)
        _emit_trace(
            trace_callback,
            "select_sources",
            "ok" if source_selection_plan else "empty",
            f"Selected {len(selected_providers)} source provider(s).",
            outputs={
                "selected_providers": selected_providers,
                "claim_source_selections": [
                    {
                        "claim_id": item.get("claim_id"),
                        "selected_sources": item.get("selected_sources", []),
                        "method": item.get("method"),
                    }
                    for item in source_selection_plan
                ],
            },
        )

        if fact_checkable_claims:
            search_client = SearchClient(self.config, extra_queries=extra_queries or [])
            _emit_trace(
                trace_callback,
                "retrieve",
                "running",
                "Retrieving candidate evidence from selected sources.",
                outputs={"selected_providers": selected_providers},
            )
            results, search_notes = search_client.search_financial_sources(
                claim=claim,
                ticker=ticker,
                argument_type=classification.argument_type,
                max_sources=max_sources,
                as_of_date=as_of,
                prefetched_results=prefetched_results,
                selected_sources=selected_providers,
            )
        else:
            results, search_notes = [], ["retrieval skipped because no fact-checkable claims were found"]
        if fact_checkable_claims and not results:
            risk_flags.append("search_unavailable")
        _emit_trace(
            trace_callback,
            "retrieve",
            "ok" if results else "empty",
            f"Retrieved {len(results)} candidate source(s).",
            outputs={"urls": [item.url for item in results], "notes": search_notes},
        )

        extractor = EvidenceExtractor(self.config)
        _emit_trace(
            trace_callback,
            "extract_evidence",
            "running",
            "Normalizing retrieved results into evidence objects.",
        )
        evidence, extraction_notes = extractor.extract(
            claim=claim,
            ticker=ticker,
            search_results=results,
            as_of_date=as_of,
            max_sources=max_sources,
        )
        _emit_trace(
            trace_callback,
            "extract_evidence",
            "ok" if evidence else "empty",
            f"Built {len(evidence)} normalized evidence object(s).",
            outputs={"domains": sorted({item.domain for item in evidence}), "notes": extraction_notes},
        )

        _emit_trace(
            trace_callback,
            "judge_evidence",
            "running",
            "Judging evidence support and reasoning quality.",
            outputs={"evidence_count": len(evidence)},
        )
        self._judge_evidence(claim, classification.argument_type, evidence)
        _emit_trace(
            trace_callback,
            "judge_evidence",
            "ok" if evidence else "empty",
            f"Judged support for {len(evidence)} evidence item(s).",
            outputs={
                "support": [
                    {"url": item.url, "support_label": item.support_label, "support_score": item.support_score}
                    for item in evidence
                ]
            },
        )
        self._score_independence(evidence)

        breakdown, verdict, label, final_flags = aggregate_scores(
            classification.argument_type,
            evidence,
            risk_flags,
        )
        _emit_trace(
            trace_callback,
            "score_pack",
            "ok",
            f"Computed credibility label {label.value}.",
            outputs={"verdict": verdict, "label": label, "score": breakdown.final_score, "risk_flags": final_flags},
        )
        _emit_trace(
            trace_callback,
            "run_verification_checks",
            "running",
            "Running numeric, logic, and source verification checks.",
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
        _emit_trace(
            trace_callback,
            "run_verification_checks",
            "ok",
            "Completed numeric, logic, and source checks.",
            outputs={
                "numeric": numeric_check.verdict if numeric_check else None,
                "logic": logic_check.verdict if logic_check else None,
                "source": source_check.verdict if source_check else None,
                "overall": overall_conclusion.overall_label if overall_conclusion else None,
            },
        )
        entity_resolution = resolve_entity(ticker, evidence=evidence, search_results=results)
        _emit_trace(
            trace_callback,
            "resolve_entity",
            "ok" if entity_resolution.confidence >= 0.70 else "review",
            f"Resolved entity as {entity_resolution.entity_id}.",
            outputs={
                "ticker": entity_resolution.ticker,
                "cik": entity_resolution.cik,
                "lei": entity_resolution.lei,
                "confidence": entity_resolution.confidence,
                "issues": entity_resolution.issues,
            },
        )
        canonical_facts = canonicalize_search_results(results, ticker, entity_resolution)
        if not canonical_facts:
            canonical_facts = canonicalize_evidence(evidence, ticker, entity_resolution)
        _emit_trace(
            trace_callback,
            "canonicalize_facts",
            "ok" if canonical_facts else "empty",
            f"Created {len(canonical_facts)} canonical fact(s).",
            outputs={"fact_ids": [fact.fact_id for fact in canonical_facts[:20]]},
        )
        _emit_trace(
            trace_callback,
            "verify_atomic_claims",
            "running",
            "Verifying each atomic claim against canonical facts and evidence.",
            outputs={"atomic_claim_count": len(planned_atomic_claims)},
        )
        atomic_claims = verify_atomic_claims(
            claim=claim,
            evidence=evidence,
            canonical_facts=canonical_facts,
            entity_resolution=entity_resolution,
            judge=self.judge,
        )
        if any(item.human_review_required for item in atomic_claims):
            final_flags = sorted(set(final_flags + ["human_review_required"]))
        _emit_trace(
            trace_callback,
            "verify_atomic_claims",
            "review" if any(result.human_review_required for result in atomic_claims) else "ok",
            f"Verified {len(atomic_claims)} atomic claim(s).",
            outputs={
                "verdicts": {
                    result.atomic_claim.claim_id: result.verdict for result in atomic_claims
                },
                "review_reasons": {
                    result.atomic_claim.claim_id: result.review_reasons
                    for result in atomic_claims
                    if result.review_reasons
                },
            },
        )
        audit_trace = build_audit_trace(
            claim=claim,
            ticker=ticker,
            as_of_date=as_of,
            search_results=results,
            evidence=evidence,
            canonical_facts=canonical_facts,
            entity_resolution=entity_resolution,
            atomic_results=atomic_claims,
            search_notes=search_notes,
            extraction_notes=extraction_notes,
        )
        _emit_trace(
            trace_callback,
            "build_audit_trace",
            "ok",
            f"Built replayable audit trace {audit_trace.trace_id}.",
            outputs={"trace_id": audit_trace.trace_id, "event_count": len(audit_trace.events)},
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
            atomic_claims=atomic_claims,
            canonical_facts=canonical_facts,
            entity_resolution=entity_resolution,
            audit_trace=audit_trace,
            evidence=evidence,
            risk_flags=final_flags,
            mode=mode,
            metadata={
                "classification_signals": classification.signals,
                "needs_decomposition": classification.needs_decomposition,
                "search_notes": search_notes,
                "extraction_notes": extraction_notes,
                "source_selection": source_selection_plan,
                "selected_providers": selected_providers,
                "source_routes": [
                    {
                        "claim_id": item.atomic_claim.claim_id,
                        **route_sources(item.atomic_claim),
                    }
                    for item in atomic_claims
                ],
            },
        )

    def _judge_evidence(self, claim: str, argument_type, evidence: list) -> None:
        """Mutate each evidence item with support and reasoning judgments."""
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
        """Score whether evidence items appear independent from each other."""
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


def _emit_trace(
    callback: Callable[[dict[str, Any]], None] | None,
    step: str,
    status: str,
    summary: str,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
) -> None:
    if not callback:
        return
    callback(
        {
            "step": step,
            "status": status,
            "summary": summary,
            "inputs": to_plain(inputs or {}),
            "outputs": to_plain(outputs or {}),
        }
    )
