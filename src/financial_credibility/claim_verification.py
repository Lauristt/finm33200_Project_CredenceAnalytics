"""Claim-level verification built on the existing evidence pipeline."""

from __future__ import annotations

from .claims import decompose_claims
from .derivations import derive_numeric_check
from .models import (
    AtomicClaim,
    AtomicClaimResult,
    CanonicalFact,
    EntityResolution,
    Evidence,
    NumericDerivation,
    VerificationCheck,
    VerificationVerdict,
)
from .rubrics import FACTUAL_TYPES
from .uncertainty import calibrate_uncertainty
from .verification import verify_logic_claim, verify_numeric_claim


def verify_atomic_claims(
    claim: str,
    evidence: list[Evidence],
    canonical_facts: list[CanonicalFact],
    entity_resolution: EntityResolution,
    judge=None,
) -> list[AtomicClaimResult]:
    """Run verification, uncertainty, and HITL rules for each atomic claim."""
    results = []
    for atomic_claim in decompose_claims(claim):
        if atomic_claim.argument_type not in FACTUAL_TYPES:
            results.append(
                AtomicClaimResult(
                    atomic_claim=atomic_claim,
                    verdict=VerificationVerdict.NOT_APPLICABLE,
                    issues=[f"Skipped non-factual claim type: {atomic_claim.argument_type.value}"],
                )
            )
            continue
        relevant_evidence = _relevant_evidence(atomic_claim, evidence)
        relevant_facts = _relevant_facts(atomic_claim, canonical_facts)
        numeric_check = verify_numeric_claim(atomic_claim.text, relevant_evidence, judge)
        logic_check = verify_logic_claim(atomic_claim.text, relevant_evidence, atomic_claim.argument_type, judge)
        derivation = derive_numeric_check(atomic_claim.text, relevant_facts, numeric_check)
        effective_numeric_check = _numeric_check_with_derivation(numeric_check, derivation)
        components, needs_review, review_reasons, issues = calibrate_uncertainty(
            atomic_claim=atomic_claim,
            evidence=relevant_evidence,
            canonical_facts=relevant_facts,
            entity_resolution=entity_resolution,
            numeric_check=effective_numeric_check,
            logic_check=logic_check,
        )
        results.append(
            AtomicClaimResult(
                atomic_claim=atomic_claim,
                verdict=_claim_verdict(effective_numeric_check.verdict, logic_check.verdict, derivation),
                evidence_urls=[item.url for item in relevant_evidence[:5]],
                evidence_keys=[_evidence_key(item) for item in relevant_evidence[:5]],
                canonical_fact_ids=[fact.fact_id for fact in relevant_facts[:10]],
                numeric_derivation=derivation,
                confidence_components=components,
                human_review_required=needs_review,
                review_reasons=review_reasons,
                issues=issues,
            )
        )
    return results


def _claim_verdict(
    numeric_verdict: str,
    logic_verdict: str,
    derivation: NumericDerivation | None = None,
) -> VerificationVerdict:
    if derivation and derivation.expression != "numeric_match_summary":
        if derivation.passed is True:
            return VerificationVerdict.SUPPORTED
        if derivation.passed is False:
            return VerificationVerdict.CONTRADICTED
    if VerificationVerdict.CONTRADICTED.value in {numeric_verdict, logic_verdict}:
        return VerificationVerdict.CONTRADICTED
    if numeric_verdict == VerificationVerdict.VERIFIED.value and logic_verdict in {
        VerificationVerdict.SUPPORTED.value,
        VerificationVerdict.PARTIALLY_SUPPORTED.value,
    }:
        return VerificationVerdict.SUPPORTED
    if logic_verdict == VerificationVerdict.SUPPORTED.value and numeric_verdict in {
        VerificationVerdict.NOT_APPLICABLE.value,
        VerificationVerdict.PARTIALLY_VERIFIED.value,
        VerificationVerdict.VERIFIED.value,
    }:
        return VerificationVerdict.SUPPORTED
    if numeric_verdict == VerificationVerdict.NOT_FOUND.value or logic_verdict == VerificationVerdict.PARTIALLY_SUPPORTED.value:
        return VerificationVerdict.PARTIALLY_SUPPORTED
    if VerificationVerdict.INSUFFICIENT.value in {numeric_verdict, logic_verdict}:
        return VerificationVerdict.INSUFFICIENT
    return VerificationVerdict.PARTIALLY_SUPPORTED


def _numeric_check_with_derivation(
    numeric_check: VerificationCheck,
    derivation: NumericDerivation | None,
) -> VerificationCheck:
    if not derivation or derivation.expression == "numeric_match_summary" or derivation.passed is None:
        return numeric_check
    verdict = VerificationVerdict.VERIFIED.value if derivation.passed else VerificationVerdict.CONTRADICTED.value
    return VerificationCheck(
        check_type="numeric_derivation",
        verdict=verdict,
        confidence=0.93 if derivation.passed else 0.88,
        summary=f"Derived metric recomputed with formula: {derivation.expression}.",
        issues=numeric_check.issues,
        method="deterministic_derivation",
    )


def _relevant_evidence(atomic_claim: AtomicClaim, evidence: list[Evidence]) -> list[Evidence]:
    """Keep broad recall for MVP, with official and relevant snippets first."""
    return sorted(
        evidence,
        key=lambda item: (
            item.is_official_primary,
            _text_overlap_hint(atomic_claim.text, item.title + " " + item.text),
            item.numeric_consistency_score,
            item.source_authority,
        ),
        reverse=True,
    )


def _relevant_facts(atomic_claim: AtomicClaim, facts: list[CanonicalFact]) -> list[CanonicalFact]:
    return sorted(
        [fact for fact in facts if _text_overlap_hint(atomic_claim.text, " ".join([fact.fact_name or "", fact.unit or ""])) > 0],
        key=lambda fact: (_tier_rank(fact.authority_tier.value), fact.parser_confidence),
        reverse=True,
    ) or facts


def _text_overlap_hint(left: str, right: str) -> float:
    left_tokens = {token for token in left.lower().replace("-", " ").split() if len(token) > 2}
    right_tokens = {token for token in right.lower().replace("-", " ").split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _evidence_key(item: Evidence) -> str:
    return f"{item.source_tier.value}:{item.domain}:{item.published_at or 'undated'}"


def _tier_rank(value: str) -> int:
    return {"T1": 5, "T2": 4, "T3": 3, "T4": 2, "T5": 1}.get(value, 0)
