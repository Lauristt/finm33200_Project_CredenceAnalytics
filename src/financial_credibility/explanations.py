"""User-facing explanation helpers for reports and audit surfaces."""

from __future__ import annotations

from typing import Any


HUMAN_REVIEW_REASON_DESCRIPTIONS = {
    "no_official_primary_source": {
        "title": "No official primary source found",
        "description": "The verifier did not find a regulator, filing, or official data source strong enough for this claim.",
        "recommended_action": "Review the claim manually or provide an official filing or data source.",
    },
    "non_official_sources_only": {
        "title": "Only non-official sources were found",
        "description": "The available evidence is not from an official primary source.",
        "recommended_action": "Check company filings, regulator data, or official statistical releases before relying on the result.",
    },
    "official_source_conflict": {
        "title": "Official sources conflict",
        "description": "Official evidence contains both supporting and contradicting signals.",
        "recommended_action": "Inspect the underlying filings, periods, units, and amended reports.",
    },
    "amended_or_restatement_or_vintage_revision": {
        "title": "Revision or restatement signal",
        "description": "The evidence mentions amended filings, restatements, or vintage revisions.",
        "recommended_action": "Confirm which filing version or data vintage should be used.",
    },
    "low_entity_resolution_confidence": {
        "title": "Low entity-resolution confidence",
        "description": "The system is not fully confident that the claim was matched to the correct entity.",
        "recommended_action": "Verify the ticker, CIK, LEI, or issuer name manually.",
    },
    "low_retrieval_sufficiency": {
        "title": "Limited evidence coverage",
        "description": "The retrieved evidence is too limited for a high-confidence automated result.",
        "recommended_action": "Retrieve additional official evidence or narrow the claim period and metric.",
    },
    "ambiguous_unit_currency_or_period": {
        "title": "Ambiguous unit, currency, or period",
        "description": "The claim contains numeric information, but the matching unit, currency, or reporting period is not clear enough.",
        "recommended_action": "Check whether the claim refers to quarterly, annual, trailing, currency-adjusted, or per-share values.",
    },
    "explanation_claim_needs_human_review": {
        "title": "Explanation or causal claim needs review",
        "description": "The claim includes an explanation such as 'driven by' or 'because', which requires stronger textual support.",
        "recommended_action": "Review management commentary or official narrative disclosures.",
    },
}


def explain_review_reason(code: str) -> dict[str, str]:
    """Return a stable user-facing explanation for a human-review reason code."""
    known = HUMAN_REVIEW_REASON_DESCRIPTIONS.get(code)
    if known:
        return {"code": code, **known}
    return {
        "code": code,
        "title": "Human review recommended",
        "description": f"The verifier raised the review flag `{code}`.",
        "recommended_action": "Inspect the evidence and audit trace before relying on this result.",
    }


def explain_review_reasons(codes: list[str]) -> list[dict[str, str]]:
    """Explain a list of reason codes while preserving order and removing duplicates."""
    seen: set[str] = set()
    explanations = []
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        explanations.append(explain_review_reason(code))
    return explanations


def build_claim_explanation(result: dict[str, Any], evidence_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a compact explanation for one atomic claim result."""
    claim = result.get("atomic_claim") or {}
    claim_id = str(claim.get("claim_id") or "claim")
    verdict = str(result.get("verdict") or "unknown")
    evidence_urls = result.get("evidence_urls") or []
    evidence_keys = result.get("evidence_keys") or []
    main_evidence = _main_evidence(evidence_urls, evidence_keys, evidence_lookup)
    confidence = (result.get("confidence_components") or {}).get("final_confidence")
    caveats = _claim_caveats(result)

    return {
        "claim_id": claim_id,
        "claim": claim.get("text", ""),
        "verdict": verdict,
        "confidence": confidence,
        "summary": _claim_summary(verdict, main_evidence, confidence),
        "numeric_summary": _numeric_summary(result.get("numeric_derivation")),
        "source_summary": _source_summary(main_evidence),
        "main_evidence": main_evidence,
        "caveats": caveats,
    }


def _main_evidence(
    evidence_urls: list[str],
    evidence_keys: list[str],
    evidence_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    for url in evidence_urls:
        if url in evidence_lookup:
            return evidence_lookup[url]
    if evidence_keys:
        return {"title": evidence_keys[0], "url": "", "source_tier": "", "is_official_primary": False}
    return None


def _claim_summary(verdict: str, evidence: dict[str, Any] | None, confidence: Any) -> str:
    source_phrase = "available evidence"
    if evidence:
        source_phrase = f"{evidence.get('title') or evidence.get('url') or 'the main evidence'}"
    confidence_phrase = ""
    if confidence is not None:
        try:
            confidence_phrase = f" with confidence {float(confidence):.2f}"
        except (TypeError, ValueError):
            confidence_phrase = f" with confidence {confidence}"
    return f"The claim is marked `{verdict}` based on {source_phrase}{confidence_phrase}."


def _numeric_summary(derivation: dict[str, Any] | None) -> str:
    if not derivation:
        return "No deterministic numeric derivation was attached to this claim."
    expression = derivation.get("expression") or "numeric check"
    inputs = derivation.get("inputs") or {}
    passed = derivation.get("passed")
    if expression == "numeric_match_summary":
        matched = _numeric_value_list(str(inputs.get("matched_values") or ""))
        unmatched = _numeric_value_list(str(inputs.get("unmatched_values") or ""))
        if passed is True and matched:
            return f"The evidence directly matches { _join_human_list(matched) } from the claim."
        if passed is False and matched and unmatched:
            return f"The evidence matches { _join_human_list(matched) }, but it does not clearly confirm { _join_human_list(unmatched) }."
        if passed is False and unmatched:
            return f"The evidence does not clearly confirm { _join_human_list(unmatched) } from the claim."
    if passed is True:
        return f"The numeric derivation `{expression}` passed."
    if passed is False:
        return f"The numeric derivation `{expression}` did not pass."
    return f"A numeric derivation summary was recorded as `{expression}`."


def _numeric_value_list(value: str) -> list[str]:
    text = value.strip()
    if not text or text.lower() == "none":
        return []
    values = []
    for item in text.split(";"):
        cleaned = item.strip()
        if not cleaned:
            continue
        values.append((cleaned.split("->", 1)[0] or cleaned).strip())
    return values[:4]


def _join_human_list(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _source_summary(evidence: dict[str, Any] | None) -> str:
    if not evidence:
        return "No direct evidence was linked to this claim."
    official = "official primary" if evidence.get("is_official_primary") else "non-official or secondary"
    tier = evidence.get("source_tier") or "unknown tier"
    return f"The main evidence is {official} evidence with source tier {tier}."


def _claim_caveats(result: dict[str, Any]) -> list[str]:
    caveats = []
    review_reasons = result.get("review_reasons") or []
    if review_reasons:
        caveats.append("Human review is recommended for this claim.")
    issues = result.get("issues") or []
    caveats.extend(_user_facing_issue(str(issue)) for issue in issues)
    if not result.get("evidence_urls") and not result.get("evidence_keys"):
        caveats.append("No claim-linked evidence was available.")
    return list(dict.fromkeys(item for item in caveats if item))[:4]


def _user_facing_issue(issue: str) -> str:
    """Return a user-facing caveat, hiding internal provider/debug failures."""
    text = " ".join(str(issue or "").split())
    if not text:
        return ""
    lower = text.lower()
    if "http error" in lower or "bad request" in lower or "fallback:" in lower:
        return ""
    if text == "llm_judge_unavailable":
        return ""
    if text == "ticker_only_entity_resolution":
        return "Entity resolution is based mainly on the ticker symbol."
    return text
