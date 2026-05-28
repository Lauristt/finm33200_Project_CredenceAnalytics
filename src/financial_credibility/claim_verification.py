"""Claim-level verification built on the existing evidence pipeline."""

from __future__ import annotations

import re

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
from .price_history import needs_historical_price_data
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
    """Return only evidence whose text is topically connected to the atomic claim."""
    scored = [
        (_text_overlap_hint(atomic_claim.text, item.title + " " + item.text), item)
        for item in evidence
    ]
    relevant = [
        (score, item)
        for score, item in scored
        if score > 0 or (_is_price_history_evidence(item) and needs_historical_price_data(atomic_claim.text))
    ]
    return [
        item
        for score, item in sorted(
            relevant,
            key=lambda pair: (
                pair[1].is_official_primary,
                pair[0],
                pair[1].numeric_consistency_score,
                pair[1].source_authority,
            ),
            reverse=True,
        )
    ]


def _is_price_history_evidence(item: Evidence) -> bool:
    text = f"{item.title} {item.text}".lower()
    return (
        "historical prices" in text
        or "historical daily close prices" in text
        or "latest_daily_return_pct" in text
        or "latest quote" in text
    )


def _relevant_facts(atomic_claim: AtomicClaim, facts: list[CanonicalFact]) -> list[CanonicalFact]:
    required_aliases = _required_fact_aliases_for_claim(atomic_claim.text)
    return sorted(
        [
            fact
            for fact in facts
            if _text_overlap_hint(atomic_claim.text, " ".join([fact.fact_name or "", fact.unit or ""])) > 0
            or (fact.fact_name or "").lower() in required_aliases
        ],
        key=lambda fact: (_tier_rank(fact.authority_tier.value), fact.parser_confidence),
        reverse=True,
    )


def _text_overlap_hint(left: str, right: str) -> float:
    left_tokens = _claim_relevance_tokens(left)
    right_tokens = _claim_relevance_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


_RELEVANCE_STOPWORDS = {
    "about",
    "access",
    "after",
    "also",
    "and",
    "another",
    "april",
    "because",
    "been",
    "before",
    "being",
    "central",
    "company",
    "corp",
    "corporation",
    "data",
    "during",
    "fact",
    "facts",
    "filing",
    "for",
    "from",
    "fiscal",
    "give",
    "gives",
    "had",
    "has",
    "have",
    "inc",
    "into",
    "its",
    "last",
    "market",
    "new",
    "not",
    "quarter",
    "previous",
    "said",
    "says",
    "sec",
    "source",
    "the",
    "that",
    "this",
    "through",
    "was",
    "were",
    "while",
    "with",
}

_RELEVANCE_ALIASES = {
    "revenues": "revenue",
    "sales": "revenue",
    "earnings": "income",
    "processors": "processor",
    "cpus": "cpu",
    "shares": "share",
    "stockpiles": "inventory",
}


def _claim_relevance_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9]+", text.lower().replace("-", " "))
    normalized = set()
    for token in tokens:
        token = _RELEVANCE_ALIASES.get(token, token)
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        if len(token) <= 2 or token in _RELEVANCE_STOPWORDS:
            continue
        normalized.add(token)
    return normalized


def _required_fact_aliases_for_claim(text: str) -> set[str]:
    lower = text.lower()
    aliases: set[str] = set()
    if "gross margin" in lower:
        aliases.update({"grossprofit", "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet"})
    if "operating margin" in lower:
        aliases.update({"operatingincomeloss", "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet"})
    if "net margin" in lower:
        aliases.update({"netincomeloss", "revenues", "revenuefromcontractwithcustomerexcludingassessedtax", "salesrevenuenet"})
    if "free cash flow" in lower or "fcf" in lower:
        aliases.update({"netcashprovidedbyusedinoperatingactivities", "paymentstoacquirepropertyplantandequipment"})
    if "current ratio" in lower:
        aliases.update({"assetscurrent", "liabilitiescurrent"})
    if "net debt" in lower:
        aliases.update(
            {
                "longtermdebt",
                "longtermdebtcurrent",
                "shorttermborrowings",
                "shorttermdebt",
                "cashandcashequivalentsatcarryingvalue",
                "cashcashequivalentsrestrictedcashandrestrictedcashequivalents",
            }
        )
    return aliases


def _evidence_key(item: Evidence) -> str:
    return f"{item.source_tier.value}:{item.domain}:{item.published_at or 'undated'}"


def _tier_rank(value: str) -> int:
    return {"T1": 5, "T2": 4, "T3": 3, "T4": 2, "T5": 1}.get(value, 0)
