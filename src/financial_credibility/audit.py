"""Audit trace construction for replayable financial verification."""

from __future__ import annotations

import hashlib

from .models import (
    AtomicClaimResult,
    AuditEvent,
    AuditTrace,
    CanonicalFact,
    EntityResolution,
    Evidence,
    SearchResult,
)


def build_audit_trace(
    claim: str,
    ticker: str,
    as_of_date: str,
    search_results: list[SearchResult],
    evidence: list[Evidence],
    canonical_facts: list[CanonicalFact],
    entity_resolution: EntityResolution,
    atomic_results: list[AtomicClaimResult],
    search_notes: list[str],
    extraction_notes: list[str],
) -> AuditTrace:
    """Create a compact trace for inspection and deterministic replay."""
    trace = AuditTrace.create(
        trace_id=_trace_id(claim, ticker, as_of_date),
        replayable_inputs={
            "claim": claim,
            "ticker": ticker.upper(),
            "as_of_date": as_of_date,
            "search_result_urls": [item.url for item in search_results],
        },
    )
    return AuditTrace(
        trace_id=trace.trace_id,
        created_at=trace.created_at,
        replayable_inputs=trace.replayable_inputs,
        source_notes=search_notes + extraction_notes,
        events=[
            AuditEvent(
                step="retrieve",
                status="ok" if search_results else "empty",
                summary=f"Retrieved {len(search_results)} candidate source(s).",
                outputs={"urls": [item.url for item in search_results]},
            ),
            AuditEvent(
                step="extract_evidence",
                status="ok" if evidence else "empty",
                summary=f"Built {len(evidence)} normalized evidence object(s).",
                outputs={"domains": sorted({item.domain for item in evidence})},
            ),
            AuditEvent(
                step="resolve_entity",
                status="ok" if entity_resolution.confidence >= 0.70 else "review",
                summary=f"Resolved entity as {entity_resolution.entity_id}.",
                outputs={
                    "ticker": entity_resolution.ticker,
                    "cik": entity_resolution.cik,
                    "lei": entity_resolution.lei,
                    "confidence": entity_resolution.confidence,
                    "issues": entity_resolution.issues,
                },
            ),
            AuditEvent(
                step="canonicalize_facts",
                status="ok" if canonical_facts else "empty",
                summary=f"Created {len(canonical_facts)} canonical fact(s).",
                outputs={"fact_ids": [fact.fact_id for fact in canonical_facts[:20]]},
            ),
            AuditEvent(
                step="verify_atomic_claims",
                status="review" if any(result.human_review_required for result in atomic_results) else "ok",
                summary=f"Verified {len(atomic_results)} atomic claim(s).",
                outputs={
                    "verdicts": {
                        result.atomic_claim.claim_id: result.verdict.value for result in atomic_results
                    },
                    "review_reasons": {
                        result.atomic_claim.claim_id: result.review_reasons
                        for result in atomic_results
                        if result.review_reasons
                    },
                },
            ),
        ],
    )


def _trace_id(claim: str, ticker: str, as_of_date: str) -> str:
    payload = f"{ticker.upper()}|{as_of_date}|{claim}"
    return "trace_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
