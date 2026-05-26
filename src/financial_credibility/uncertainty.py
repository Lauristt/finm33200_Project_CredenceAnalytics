"""Confidence decomposition and human-review escalation rules."""

from __future__ import annotations

import re
from statistics import mean

from .models import (
    AtomicClaim,
    CanonicalFact,
    ConfidenceComponents,
    EntityResolution,
    Evidence,
    SupportLabel,
    VerificationCheck,
    VerificationVerdict,
    clamp,
)
from .sources import extract_substantive_numbers


def calibrate_uncertainty(
    atomic_claim: AtomicClaim,
    evidence: list[Evidence],
    canonical_facts: list[CanonicalFact],
    entity_resolution: EntityResolution,
    numeric_check: VerificationCheck,
    logic_check: VerificationCheck,
) -> tuple[ConfidenceComponents, bool, list[str], list[str]]:
    """Return explainable confidence and deterministic human-review triggers."""
    official_evidence = [item for item in evidence if item.is_official_primary]
    source_authority = _mean_or_zero([item.source_authority for item in evidence])
    entity_match = max(
        entity_resolution.confidence,
        _mean_or_zero([item.entity_match_score for item in evidence]),
    )
    time_alignment = _mean_or_zero([item.recency_score for item in evidence]) if evidence else 0.0
    numeric_exactness = _numeric_exactness(atomic_claim, numeric_check)
    retrieval_sufficiency = _retrieval_sufficiency(evidence, canonical_facts)
    cross_source_consistency = _cross_source_consistency(evidence)
    parser_confidence = _mean_or_zero([fact.parser_confidence for fact in canonical_facts])

    final = round(
        clamp(
            0.20 * source_authority
            + 0.15 * entity_match
            + 0.10 * time_alignment
            + 0.20 * numeric_exactness
            + 0.15 * retrieval_sufficiency
            + 0.10 * cross_source_consistency
            + 0.10 * parser_confidence
        ),
        3,
    )
    components = ConfidenceComponents(
        source_authority=round(source_authority, 3),
        entity_match=round(entity_match, 3),
        time_alignment=round(time_alignment, 3),
        numeric_exactness=round(numeric_exactness, 3),
        retrieval_sufficiency=round(retrieval_sufficiency, 3),
        cross_source_consistency=round(cross_source_consistency, 3),
        parser_confidence=round(parser_confidence, 3),
        final_confidence=final,
    )

    review_reasons = _review_reasons(
        atomic_claim=atomic_claim,
        evidence=evidence,
        official_evidence=official_evidence,
        canonical_facts=canonical_facts,
        entity_resolution=entity_resolution,
        components=components,
        numeric_check=numeric_check,
        logic_check=logic_check,
    )
    issues = list(dict.fromkeys(entity_resolution.issues + numeric_check.issues + logic_check.issues))
    return components, bool(review_reasons), review_reasons, issues


def _review_reasons(
    atomic_claim: AtomicClaim,
    evidence: list[Evidence],
    official_evidence: list[Evidence],
    canonical_facts: list[CanonicalFact],
    entity_resolution: EntityResolution,
    components: ConfidenceComponents,
    numeric_check: VerificationCheck,
    logic_check: VerificationCheck,
) -> list[str]:
    reasons: list[str] = []
    if not official_evidence and not any(fact.authority_tier.value in {"T1", "T2"} for fact in canonical_facts):
        reasons.append("no_official_primary_source")
    if evidence and not official_evidence:
        reasons.append("non_official_sources_only")
    if _has_official_conflict(evidence):
        reasons.append("official_source_conflict")
    if _mentions_revision(evidence, canonical_facts):
        reasons.append("amended_or_restatement_or_vintage_revision")
    if entity_resolution.confidence < 0.70:
        reasons.append("low_entity_resolution_confidence")
    if components.retrieval_sufficiency < 0.45:
        reasons.append("low_retrieval_sufficiency")
    if _has_ambiguous_unit_period(atomic_claim, canonical_facts, numeric_check):
        reasons.append("ambiguous_unit_currency_or_period")
    if _is_explanation_claim(atomic_claim.text) and logic_check.confidence < 0.72:
        reasons.append("explanation_claim_needs_human_review")
    return list(dict.fromkeys(reasons))


def _numeric_exactness(atomic_claim: AtomicClaim, numeric_check: VerificationCheck) -> float:
    if numeric_check.verdict == VerificationVerdict.NOT_APPLICABLE.value:
        return 0.65 if not extract_substantive_numbers(atomic_claim.text) else 0.35
    return numeric_check.confidence


def _retrieval_sufficiency(evidence: list[Evidence], canonical_facts: list[CanonicalFact]) -> float:
    if not evidence and not canonical_facts:
        return 0.0
    official_count = sum(1 for item in evidence if item.is_official_primary)
    canonical_bonus = 0.20 if canonical_facts else 0.0
    if official_count >= 2:
        return min(1.0, 0.80 + canonical_bonus)
    if official_count == 1:
        return min(1.0, 0.62 + canonical_bonus)
    return 0.35


def _cross_source_consistency(evidence: list[Evidence]) -> float:
    if not evidence:
        return 0.0
    supporting = [item for item in evidence if item.support_label == SupportLabel.SUPPORTS]
    contradicting = [item for item in evidence if item.support_label == SupportLabel.CONTRADICTS]
    if supporting and contradicting:
        return 0.25
    if len({item.domain for item in evidence}) >= 2:
        return 0.78
    return 0.55


def _has_official_conflict(evidence: list[Evidence]) -> bool:
    official = [item for item in evidence if item.is_official_primary]
    return any(item.support_label == SupportLabel.SUPPORTS for item in official) and any(
        item.support_label == SupportLabel.CONTRADICTS for item in official
    )


def _mentions_revision(evidence: list[Evidence], canonical_facts: list[CanonicalFact]) -> bool:
    haystack = " ".join(f"{item.title} {item.text}" for item in evidence).lower()
    if re.search(r"\b(amended|restated|restatement|10-k/a|10-q/a|revision|vintage)\b", haystack):
        return True
    return any(str(fact.raw.get("form", "")).upper().endswith("/A") or fact.vintage_date for fact in canonical_facts)


def _has_ambiguous_unit_period(
    atomic_claim: AtomicClaim,
    canonical_facts: list[CanonicalFact],
    numeric_check: VerificationCheck,
) -> bool:
    if not extract_substantive_numbers(atomic_claim.text):
        return False
    if numeric_check.verdict == VerificationVerdict.VERIFIED.value:
        return False
    if not canonical_facts:
        return True
    if _has_duplicate_period_values(canonical_facts):
        return True
    return any(not fact.unit and fact.value is not None for fact in canonical_facts)


def _is_explanation_claim(text: str) -> bool:
    return bool(re.search(r"\b(due to|because|driven by|mainly|primarily|from|attributable to|主要|来自|由于)\b", text, re.IGNORECASE))


def _has_duplicate_period_values(facts: list[CanonicalFact]) -> bool:
    seen: dict[tuple[str, str], set[str]] = {}
    for fact in facts:
        if not fact.fact_name or not fact.report_period or fact.value is None:
            continue
        key = (fact.fact_name, fact.report_period)
        seen.setdefault(key, set()).add(str(fact.value))
    return any(len(values) > 1 for values in seen.values())


def _mean_or_zero(values: list[float]) -> float:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return 0.0
    return mean(cleaned)
