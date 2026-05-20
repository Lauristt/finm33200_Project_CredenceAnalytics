from __future__ import annotations

import re
from statistics import mean

from .models import (
    ArgumentType,
    Evidence,
    OverallConclusion,
    ScoreBreakdown,
    VerificationCheck,
    VerificationVerdict,
    clamp,
)
from .rubrics import FACTUAL_TYPES
from .sources import extract_numbers


def verify_numeric_claim(claim: str, evidence: list[Evidence], judge=None) -> VerificationCheck:
    """Verify numeric claims with fuzzy local matching first, then optional LLM fallback."""
    claim_numbers = extract_numbers(claim)
    if not claim_numbers:
        return VerificationCheck(
            check_type="numeric_check",
            verdict=VerificationVerdict.NOT_APPLICABLE.value,
            confidence=0.75,
            summary="The claim does not contain explicit numeric values.",
            method="fuzzy_local",
        )

    if not evidence:
        return VerificationCheck(
            check_type="numeric_check",
            verdict=VerificationVerdict.INSUFFICIENT.value,
            confidence=0.10,
            summary="No evidence was available for numeric verification.",
            issues=["no_evidence"],
            method="fuzzy_local",
        )

    matches = _fuzzy_numeric_matches(claim_numbers, evidence)
    if matches:
        urls = sorted({url for _, _, url in matches})
        return VerificationCheck(
            check_type="numeric_check",
            verdict=VerificationVerdict.VERIFIED.value,
            confidence=0.90,
            summary="At least one numeric value in the claim was matched directly in the evidence.",
            evidence_urls=urls,
            issues=[f"matched {claim_num} with {evidence_num}" for claim_num, evidence_num, _ in matches],
            method="fuzzy_local",
        )

    if judge and hasattr(judge, "judge_numeric_claim"):
        return judge.judge_numeric_claim(claim, evidence)

    return VerificationCheck(
        check_type="numeric_check",
        verdict=VerificationVerdict.NOT_FOUND.value,
        confidence=0.35,
        summary="The numeric values in the claim were not found in the available evidence.",
        evidence_urls=[item.url for item in evidence[:3]],
        issues=[f"claim numbers not matched: {', '.join(claim_numbers)}"],
        method="fuzzy_local",
    )


def verify_logic_claim(
    claim: str,
    evidence: list[Evidence],
    argument_type: ArgumentType,
    judge=None,
) -> VerificationCheck:
    if not evidence:
        return VerificationCheck(
            check_type="logic_check",
            verdict=VerificationVerdict.INSUFFICIENT.value,
            confidence=0.10,
            summary="No evidence was available for logic verification.",
            issues=["no_evidence"],
            method="heuristic",
        )

    if judge and hasattr(judge, "judge_logic_claim"):
        return judge.judge_logic_claim(claim, evidence, argument_type)

    support = mean([item.support_score for item in evidence]) if evidence else 0.0
    reasoning = mean([item.reasoning_quality_score for item in evidence]) if evidence else 0.0
    confidence = round(clamp(0.45 * support + 0.55 * reasoning), 3)

    if argument_type in FACTUAL_TYPES:
        verdict = VerificationVerdict.SUPPORTED if support >= 0.60 else VerificationVerdict.PARTIALLY_SUPPORTED
        summary = "The claim is mostly factual; logic verification focuses on whether evidence addresses the claim."
    else:
        verdict = VerificationVerdict.SUPPORTED if confidence >= 0.70 else VerificationVerdict.PARTIALLY_SUPPORTED
        summary = "The evidence provides some reasoning support, but assumptions may still need review."

    return VerificationCheck(
        check_type="logic_check",
        verdict=verdict.value,
        confidence=confidence,
        summary=summary,
        evidence_urls=[item.url for item in evidence[:3]],
        method="heuristic",
    )


def verify_sources(evidence: list[Evidence], breakdown: ScoreBreakdown) -> VerificationCheck:
    if not evidence:
        return VerificationCheck(
            check_type="source_check",
            verdict=VerificationVerdict.INSUFFICIENT.value,
            confidence=0.0,
            summary="No sources were available.",
            issues=["no_evidence"],
            method="scoring",
        )

    source_confidence = source_confidence_from_breakdown(breakdown)
    if source_confidence >= 0.75:
        verdict = VerificationVerdict.VERIFIED
        summary = "Sources are strong enough for a useful credibility assessment."
    elif source_confidence >= 0.55:
        verdict = VerificationVerdict.PARTIALLY_VERIFIED
        summary = "Sources are usable but have limitations in authority, recency, or independence."
    else:
        verdict = VerificationVerdict.WEAK
        summary = "Sources are weak or insufficiently independent."

    return VerificationCheck(
        check_type="source_check",
        verdict=verdict.value,
        confidence=source_confidence,
        summary=summary,
        evidence_urls=[item.url for item in evidence[:5]],
        issues=_source_issues(evidence),
        method="scoring",
    )


def build_overall_conclusion(
    argument_type: ArgumentType,
    numeric_check: VerificationCheck,
    logic_check: VerificationCheck,
    source_check: VerificationCheck,
) -> OverallConclusion:
    numeric_applicable = numeric_check.verdict != VerificationVerdict.NOT_APPLICABLE.value
    if numeric_check.verdict == VerificationVerdict.CONTRADICTED.value and argument_type in FACTUAL_TYPES:
        return OverallConclusion(
            overall_label="Contradicted",
            final_confidence=round(numeric_check.confidence, 3),
            numeric_confidence=numeric_check.confidence,
            logic_confidence=logic_check.confidence,
            source_confidence=source_check.confidence,
            summary="The claim appears contradicted by the available numeric evidence.",
        )

    if numeric_applicable:
        final = (
            0.35 * numeric_check.confidence
            + 0.35 * logic_check.confidence
            + 0.30 * source_check.confidence
        )
    else:
        final = 0.55 * logic_check.confidence + 0.45 * source_check.confidence

    final = round(clamp(final), 3)
    if final >= 0.85:
        label = "Very High"
    elif final >= 0.70:
        label = "High"
    elif final >= 0.50:
        label = "Medium"
    else:
        label = "Low"

    if source_check.confidence < 0.35:
        label = "Low"

    return OverallConclusion(
        overall_label=label,
        final_confidence=final,
        numeric_confidence=round(numeric_check.confidence, 3),
        logic_confidence=round(logic_check.confidence, 3),
        source_confidence=round(source_check.confidence, 3),
        summary=_overall_summary(label, numeric_check, logic_check, source_check),
    )


def source_confidence_from_breakdown(breakdown: ScoreBreakdown) -> float:
    return round(
        clamp(
            0.50 * breakdown.source_authority
            + 0.25 * breakdown.independence
            + 0.25 * breakdown.recency
        ),
        3,
    )


def _fuzzy_numeric_matches(claim_numbers: list[str], evidence: list[Evidence]) -> list[tuple[str, str, str]]:
    matches = []
    evidence_numbers: list[tuple[str, str]] = []
    for item in evidence:
        for number in extract_numbers(f"{item.title}\n{item.text}"):
            evidence_numbers.append((number, item.url))

    for claim_number in claim_numbers:
        claim_forms = _numeric_forms(claim_number)
        for evidence_number, url in evidence_numbers:
            if claim_forms & _numeric_forms(evidence_number):
                matches.append((claim_number, evidence_number, url))
                break
    return matches


def _numeric_forms(value: str) -> set[str]:
    raw = value.lower().strip()
    compact = re.sub(r"[\s,$,]", "", raw).replace("percent", "%")
    no_unit = re.sub(r"(billion|million|trillion|bn|mn|bps|%)$", "", compact)
    forms = {compact, no_unit}
    if compact.endswith("%"):
        forms.add(compact[:-1])
    return {form for form in forms if form}


def _source_issues(evidence: list[Evidence]) -> list[str]:
    issues = []
    if len({item.domain for item in evidence}) <= 1:
        issues.append("single_source_domain")
    if max((item.source_authority for item in evidence), default=0.0) < 0.65:
        issues.append("no_high_authority_source")
    if len(evidence) < 2:
        issues.append("single_evidence_item")
    return issues


def _overall_summary(
    label: str,
    numeric_check: VerificationCheck,
    logic_check: VerificationCheck,
    source_check: VerificationCheck,
) -> str:
    return (
        f"Overall confidence is {label}. Numeric check: {numeric_check.verdict}; "
        f"logic check: {logic_check.verdict}; source check: {source_check.verdict}."
    )
