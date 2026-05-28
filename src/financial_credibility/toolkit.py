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
from .models import CredibilityLabel, EvidencePack, SearchResult, Verdict, VerificationVerdict, today_iso, to_plain
from .preprocessing import preprocess_statement
from .routing import route_sources
from .rubrics import FACTUAL_TYPES
from .search import SearchClient
from .source_selection import selected_provider_names_from_plan, select_sources_for_claims
from .time_context import infer_time_context
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
        original_claim = claim
        preprocessed = preprocess_statement(claim)
        claim = preprocessed.clean_text
        _emit_trace(
            trace_callback,
            "preprocess_statement",
            "ok" if preprocessed.changed else "unchanged",
            "Removed copied-page boilerplate before verification." if preprocessed.changed else "Input did not require preprocessing.",
            outputs=preprocessed.to_dict(),
        )
        time_context = infer_time_context(claim, as_of_date)
        as_of = time_context.effective_as_of_date or today_iso()
        _emit_trace(
            trace_callback,
            "infer_time_context",
            "ok" if time_context.effective_as_of_date else "fallback",
            f"Anchored retrieval as of {as_of}.",
            outputs=time_context.to_dict(),
        )
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
        retrieval_budget = _retrieval_budget(max_sources, fact_checkable_claims)
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
                "retrieval_budget": retrieval_budget,
            },
        )

        claim_time_contexts: list[dict[str, Any]] = []
        claim_retrievals: list[dict[str, Any]] = []
        if fact_checkable_claims and not selected_providers:
            results, search_notes = [], ["retrieval skipped because no compatible source was selected"]
            risk_flags.append("no_matching_source")
        elif fact_checkable_claims:
            search_client = SearchClient(self.config, extra_queries=extra_queries or [])
            _emit_trace(
                trace_callback,
                "retrieve",
                "running",
                "Retrieving candidate evidence from selected sources.",
                outputs={"selected_providers": selected_providers},
            )
            if prefetched_results is not None:
                results, search_notes = search_client.search_financial_sources(
                    claim=claim,
                    ticker=ticker,
                    argument_type=classification.argument_type,
                    max_sources=retrieval_budget,
                    as_of_date=as_of,
                    prefetched_results=prefetched_results,
                    selected_sources=selected_providers,
                )
                claim_time_contexts = [
                    {
                        "claim_id": item.claim_id,
                        "claim": item.text,
                        "as_of_date": as_of,
                        "time_context": infer_time_context(item.text, anchor_date=as_of).to_dict(),
                    }
                    for item in fact_checkable_claims
                ]
                claim_retrievals = [
                    {
                        "claim_id": item.claim_id,
                        "claim": item.text,
                        "selected_providers": selected_providers,
                        "retrieved_count": len(results),
                        "added_urls": [result.url for result in results[:retrieval_budget]],
                        "method": "prefetched_results_shared",
                    }
                    for item in fact_checkable_claims
                ]
            else:
                results = []
                search_notes = []
                seen_urls: set[str] = set()
                for atom, selection in zip(fact_checkable_claims, source_selection_plan):
                    providers = selection.get("selected_provider_names") or []
                    if not providers:
                        search_notes.append(f"{atom.claim_id}: retrieval skipped because no compatible source was selected")
                        claim_retrievals.append(
                            {
                                "claim_id": atom.claim_id,
                                "claim": atom.text,
                                "selected_providers": [],
                                "retrieved_count": 0,
                                "added_urls": [],
                                "method": "no_compatible_source",
                            }
                        )
                        continue
                    atom_time_context = infer_time_context(atom.text, anchor_date=as_of)
                    atom_as_of = atom_time_context.effective_as_of_date or as_of
                    claim_time_contexts.append(
                        {
                            "claim_id": atom.claim_id,
                            "claim": atom.text,
                            "as_of_date": atom_as_of,
                            "time_context": atom_time_context.to_dict(),
                            "selected_providers": providers,
                        }
                    )
                    atom_results, atom_notes = search_client.search_financial_sources(
                        claim=atom.text,
                        ticker=ticker,
                        argument_type=atom.argument_type,
                        max_sources=max_sources,
                        as_of_date=atom_as_of,
                        selected_sources=providers,
                    )
                    search_notes.extend([f"{atom.claim_id}: {note}" for note in atom_notes])
                    added_urls = []
                    for result in atom_results:
                        if result.url in seen_urls:
                            continue
                        if len(results) >= retrieval_budget:
                            search_notes.append(
                                f"{atom.claim_id}: retrieval budget reached after {retrieval_budget} unique result(s)"
                            )
                            break
                        seen_urls.add(result.url)
                        results.append(result)
                        added_urls.append(result.url)
                    claim_retrievals.append(
                        {
                            "claim_id": atom.claim_id,
                            "claim": atom.text,
                            "as_of_date": atom_as_of,
                            "selected_providers": providers,
                            "retrieved_count": len(atom_results),
                            "added_urls": added_urls,
                            "method": "per_claim_retrieval",
                        }
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
            outputs={
                "urls": [item.url for item in results],
                "notes": search_notes,
                "claim_time_contexts": claim_time_contexts,
                "claim_retrievals": claim_retrievals,
                "retrieval_budget": retrieval_budget,
            },
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
            max_sources=retrieval_budget,
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
        evidence_coverage = _build_evidence_coverage(
            atomic_claims=atomic_claims,
            source_selection_plan=source_selection_plan,
            claim_retrievals=claim_retrievals,
        )
        incomplete_coverage = [
            item
            for item in evidence_coverage
            if item["fact_checkable"] and not item["has_relevant_evidence"] and item["selected_sources"]
        ]
        _emit_trace(
            trace_callback,
            "agentic_coverage_check",
            "review" if incomplete_coverage else "ok",
            (
                "Checked whether each fact-checkable atomic claim has relevant evidence before final verdicts."
                if not incomplete_coverage
                else f"{len(incomplete_coverage)} fact-checkable claim(s) still lack relevant evidence after retrieval."
            ),
            outputs={"coverage": evidence_coverage},
        )
        if any(item.human_review_required for item in atomic_claims):
            final_flags = sorted(set(final_flags + ["human_review_required"]))
        verdict, label, final_flags = _reconcile_final_verdict(
            current_verdict=verdict,
            current_label=label,
            final_flags=final_flags,
            numeric_check=numeric_check,
            logic_check=logic_check,
            source_check=source_check,
            atomic_claims=atomic_claims,
        )
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
                "time_context": time_context.to_dict(),
                "claim_time_contexts": claim_time_contexts,
                "claim_retrievals": claim_retrievals,
                "evidence_coverage": evidence_coverage,
                "retrieval_budget": retrieval_budget,
                "source_selection": source_selection_plan,
                "selected_providers": selected_providers,
                "source_routes": [
                    {
                        "claim_id": item.atomic_claim.claim_id,
                        **route_sources(item.atomic_claim),
                    }
                    for item in atomic_claims
                ],
                "preprocessing": preprocessed.to_dict(),
                "original_claim": original_claim,
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


def _reconcile_final_verdict(
    current_verdict,
    current_label,
    final_flags: list[str],
    numeric_check,
    logic_check,
    source_check,
    atomic_claims,
):
    """Let explicit checks rescue under-supported factual claims without hiding contradictions."""
    if current_verdict != Verdict.INSUFFICIENT:
        return current_verdict, current_label, final_flags
    if numeric_check.verdict == VerificationVerdict.CONTRADICTED.value:
        return current_verdict, current_label, final_flags
    if any(item.verdict == VerificationVerdict.CONTRADICTED for item in atomic_claims):
        return current_verdict, current_label, final_flags

    fact_claims = [item for item in atomic_claims if item.verdict != VerificationVerdict.NOT_APPLICABLE]
    supportive_atomic = [
        item
        for item in fact_claims
        if item.verdict in {VerificationVerdict.SUPPORTED, VerificationVerdict.PARTIALLY_SUPPORTED}
    ]
    numeric_supportive = numeric_check.verdict in {
        VerificationVerdict.VERIFIED.value,
        VerificationVerdict.PARTIALLY_VERIFIED.value,
    }
    logic_supportive = logic_check.verdict in {
        VerificationVerdict.SUPPORTED.value,
        VerificationVerdict.PARTIALLY_SUPPORTED.value,
    }
    source_usable = source_check.confidence >= 0.55
    should_rescue = (
        bool(supportive_atomic)
        and len(supportive_atomic) == len(fact_claims)
        and source_usable
    ) or (numeric_supportive and logic_supportive and source_usable)
    if not should_rescue:
        return current_verdict, current_label, final_flags

    label = current_label
    if current_label == CredibilityLabel.LOW:
        label = (
            CredibilityLabel.HIGH
            if numeric_check.verdict == VerificationVerdict.VERIFIED.value and source_check.confidence >= 0.75
            else CredibilityLabel.MEDIUM
        )
    return Verdict.SUPPORTED, label, sorted(set(final_flags + ["verdict_reconciled_from_verification_checks"]))


def _retrieval_budget(max_sources: int, fact_checkable_claims: list) -> int:
    """Use a per-claim retrieval budget so early claims cannot starve later ones."""
    return max(1, int(max_sources)) * max(1, len(fact_checkable_claims))


def _build_evidence_coverage(
    atomic_claims,
    source_selection_plan: list[dict[str, Any]],
    claim_retrievals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize whether each atomic claim reached evidence before final judgment."""
    selection_by_id = {
        str(item.get("claim_id")): item
        for item in source_selection_plan
        if item.get("claim_id")
    }
    retrieval_by_id = {
        str(item.get("claim_id")): item
        for item in claim_retrievals
        if item.get("claim_id")
    }
    rows = []
    for result in atomic_claims:
        claim = result.atomic_claim
        selection = selection_by_id.get(claim.claim_id, {})
        retrieval = retrieval_by_id.get(claim.claim_id, {})
        selected_sources = (
            selection.get("selected_provider_names")
            or selection.get("selected_sources")
            or retrieval.get("selected_providers")
            or []
        )
        fact_checkable = claim.argument_type in FACTUAL_TYPES
        has_relevant_evidence = bool(result.evidence_urls)
        if not fact_checkable:
            status = "skipped_non_factual"
        elif has_relevant_evidence:
            status = "evidence_attached"
        elif selected_sources and retrieval.get("retrieved_count", 0):
            status = "retrieved_but_not_relevant"
        elif selected_sources:
            status = "selected_source_returned_no_data"
        else:
            status = "no_compatible_source"
        rows.append(
            {
                "claim_id": claim.claim_id,
                "claim": claim.text,
                "fact_checkable": fact_checkable,
                "selected_sources": selected_sources,
                "retrieved_count": int(retrieval.get("retrieved_count") or 0),
                "added_urls": retrieval.get("added_urls") or [],
                "evidence_url_count": len(result.evidence_urls),
                "has_relevant_evidence": has_relevant_evidence,
                "verdict": result.verdict.value,
                "human_review_required": result.human_review_required,
                "review_reasons": result.review_reasons,
                "closure_status": status,
            }
        )
    return rows


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
