"""Deterministic weighted score aggregation.

This score is the glass-box component of the toolkit. The newer
`overall_conclusion` uses explicit numeric/logic/source checks, but this module
still provides a stable rubric-backed score for comparison and reporting.
"""

from __future__ import annotations

from statistics import mean

from .models import (
    ArgumentType,
    CredibilityLabel,
    Evidence,
    ScoreBreakdown,
    SupportLabel,
    Verdict,
    clamp,
)
from .rubrics import FACTUAL_TYPES, RUBRIC_WEIGHTS


def aggregate_scores(
    argument_type: ArgumentType,
    evidence: list[Evidence],
    risk_flags: list[str] | None = None,
) -> tuple[ScoreBreakdown, Verdict, CredibilityLabel, list[str]]:
    """Aggregate evidence-level scores into a final score, verdict, and label."""
    flags = list(risk_flags or [])
    weights = RUBRIC_WEIGHTS[argument_type]

    if not evidence:
        breakdown = ScoreBreakdown(
            source_authority=0.0,
            recency=0.0,
            evidence_support=0.0,
            numeric_consistency=0.0,
            independence=0.0,
            reasoning_quality=0.0,
            penalties=0.20,
            final_score=0.0,
            weights=weights,
        )
        return breakdown, Verdict.INSUFFICIENT, CredibilityLabel.LOW, flags + ["no_evidence"]

    supporting = [item for item in evidence if item.support_label == SupportLabel.SUPPORTS]
    contradicting = [item for item in evidence if item.support_label == SupportLabel.CONTRADICTS]
    usable = supporting or evidence

    source_authority = _weighted_mean([item.source_authority for item in usable], default=0.0)
    recency = _weighted_mean([item.recency_score for item in usable], default=0.0)
    support = _support_dimension(evidence)
    numeric = _weighted_mean([item.numeric_consistency_score for item in usable], default=0.0)
    independence = _weighted_mean([item.independence_score for item in usable], default=_domain_diversity(evidence))
    reasoning = _weighted_mean([item.reasoning_quality_score for item in usable], default=0.0)
    penalties = _penalties(evidence, contradicting, flags)

    raw_score = (
        weights["source_authority"] * source_authority
        + weights["recency"] * recency
        + weights["evidence_support"] * support
        + weights["numeric_consistency"] * numeric
        + weights["independence"] * independence
        + weights["reasoning_quality"] * reasoning
        - penalties
    )
    final_score = round(clamp(raw_score), 3)

    contradiction_strength = _contradiction_strength(contradicting)
    support_strength = _support_strength(supporting)
    verdict = _verdict(argument_type, support_strength, contradiction_strength)
    label = _label(argument_type, final_score, support_strength, contradiction_strength, supporting)

    if len({item.domain for item in evidence}) <= 1:
        flags.append("single_source_domain")
    if contradicting and supporting:
        flags.append("mixed_evidence")
    if source_authority < 0.45:
        flags.append("weak_source_authority")

    breakdown = ScoreBreakdown(
        source_authority=round(source_authority, 3),
        recency=round(recency, 3),
        evidence_support=round(support, 3),
        numeric_consistency=round(numeric, 3),
        independence=round(independence, 3),
        reasoning_quality=round(reasoning, 3),
        penalties=round(penalties, 3),
        final_score=final_score,
        weights=weights,
    )
    return breakdown, verdict, label, sorted(set(flags))


def _weighted_mean(values: list[float], default: float) -> float:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return default
    return mean(cleaned)


def _support_dimension(evidence: list[Evidence]) -> float:
    if not evidence:
        return 0.0
    support_values = []
    for item in evidence:
        if item.support_label == SupportLabel.SUPPORTS:
            support_values.append(item.support_score)
        elif item.support_label == SupportLabel.CONTRADICTS:
            support_values.append(max(0.0, 0.25 - item.support_score * 0.25))
        else:
            support_values.append(item.support_score * 0.35)
    return mean(support_values)


def _domain_diversity(evidence: list[Evidence]) -> float:
    domains = {item.domain for item in evidence if item.domain}
    if not domains:
        return 0.0
    if len(domains) == 1:
        return 0.35
    return min(0.90, 0.45 + 0.15 * len(domains))


def _penalties(evidence: list[Evidence], contradicting: list[Evidence], flags: list[str]) -> float:
    penalty = 0.0
    if contradicting:
        penalty += min(0.25, 0.08 * len(contradicting))
    if any(item.entity_match_score < 0.50 for item in evidence):
        penalty += 0.05
    if "search_unavailable" in flags:
        penalty += 0.05
    return clamp(penalty, 0.0, 0.35)


def _support_strength(supporting: list[Evidence]) -> float:
    if not supporting:
        return 0.0
    return max(item.support_score * item.source_authority for item in supporting)


def _contradiction_strength(contradicting: list[Evidence]) -> float:
    if not contradicting:
        return 0.0
    return max(item.support_score * item.source_authority for item in contradicting)


def _verdict(
    argument_type: ArgumentType,
    support_strength: float,
    contradiction_strength: float,
) -> Verdict:
    if contradiction_strength >= 0.70 and argument_type in FACTUAL_TYPES:
        return Verdict.CONTRADICTED
    if support_strength >= 0.62 and contradiction_strength >= 0.45:
        return Verdict.MIXED
    if support_strength >= 0.55:
        return Verdict.SUPPORTED
    return Verdict.INSUFFICIENT


def _label(
    argument_type: ArgumentType,
    score: float,
    support_strength: float,
    contradiction_strength: float,
    supporting: list[Evidence],
) -> CredibilityLabel:
    if contradiction_strength >= 0.70 and argument_type in FACTUAL_TYPES:
        return CredibilityLabel.CONTRADICTED_FACT
    has_strong_primary = any(item.source_authority >= 0.80 for item in supporting)
    if score >= 0.90 and has_strong_primary and support_strength >= 0.65:
        return CredibilityLabel.VERY_HIGH
    if score >= 0.75:
        return CredibilityLabel.HIGH
    if score >= 0.55:
        return CredibilityLabel.MEDIUM
    return CredibilityLabel.LOW
