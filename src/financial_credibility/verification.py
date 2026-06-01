"""Explicit numeric, logic, source, and overall verification checks.

These checks are the main agent-facing outputs. They complement the deterministic
score in `aggregation.py` by separating the question into interpretable parts.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from .sources import extract_numbers, extract_substantive_number_spans


@dataclass(frozen=True)
class _ClaimNumber:
    value: str
    role: str = "core"


def verify_numeric_claim(claim: str, evidence: list[Evidence], judge=None) -> VerificationCheck:
    """Verify numeric claims with fuzzy local matching first, then optional LLM fallback."""
    claim_number_items = _material_claim_number_items(claim)
    claim_numbers = [item.value for item in claim_number_items]
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

    core_numbers = [item.value for item in claim_number_items if item.role == "core"]
    contextual_numbers = [item.value for item in claim_number_items if item.role != "core"]
    matches = _fuzzy_numeric_matches(claim_numbers, evidence)
    matched_claim_numbers = {claim_num for claim_num, _, _ in matches}
    unmatched_core = [claim_num for claim_num in core_numbers if claim_num not in matched_claim_numbers]
    unmatched_contextual = [claim_num for claim_num in contextual_numbers if claim_num not in matched_claim_numbers]
    matched_core_count = len([value for value in core_numbers if value in matched_claim_numbers])
    core_coverage = matched_core_count / max(len(core_numbers), 1)

    if len(matches) == len(claim_numbers) or (core_numbers and not unmatched_core):
        urls = sorted({url for _, _, url in matches})
        issues = [f"matched {claim_num} with {evidence_num}" for claim_num, evidence_num, _ in matches]
        if unmatched_contextual:
            issues.append(f"contextual forward-looking numbers not required for core verification: {', '.join(unmatched_contextual)}")
        return VerificationCheck(
            check_type="numeric_check",
            verdict=VerificationVerdict.VERIFIED.value,
            confidence=0.86 if unmatched_contextual else 0.90,
            summary=(
                "All core numeric values in the claim were matched directly in the evidence."
                if contextual_numbers
                else "All material numeric values in the claim were matched directly in the evidence."
            ),
            evidence_urls=urls,
            issues=issues,
            method="fuzzy_local",
        )

    if matches:
        unmatched = [claim_num for claim_num in claim_numbers if claim_num not in matched_claim_numbers]
        urls = sorted({url for _, _, url in matches})
        return VerificationCheck(
            check_type="numeric_check",
            verdict=VerificationVerdict.PARTIALLY_VERIFIED.value,
            confidence=round(clamp(0.56 + 0.24 * core_coverage + 0.04 * bool(contextual_numbers)), 3),
            summary="Some core numeric values in the claim were matched directly in the evidence.",
            evidence_urls=urls,
            issues=[
                *[f"matched {claim_num} with {evidence_num}" for claim_num, evidence_num, _ in matches],
                f"unmatched claim numbers: {', '.join(unmatched)}",
            ],
            method="fuzzy_local",
        )

    if judge and hasattr(judge, "judge_numeric_claim"):
        return judge.judge_numeric_claim(claim, _rank_evidence_for_verification(evidence))

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
    """Verify whether the claim's reasoning/inference is supported by evidence."""
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
        return judge.judge_logic_claim(
            claim,
            _rank_evidence_for_verification(evidence),
            argument_type,
        )

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
    """Summarize source quality using authority, independence, and recency."""
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
    """Combine explicit checks into the final English confidence label."""
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
    """Derive source-only confidence from the deterministic score breakdown."""
    return round(
        clamp(
            0.50 * breakdown.source_authority
            + 0.25 * breakdown.independence
            + 0.25 * breakdown.recency
        ),
        3,
    )


def _fuzzy_numeric_matches(claim_numbers: list[str], evidence: list[Evidence]) -> list[tuple[str, str, str]]:
    """Return claim/evidence number pairs that match after light normalization."""
    matches = []
    evidence_numbers: list[tuple[str, str]] = []
    for item in evidence:
        for number in extract_numbers(f"{item.title}\n{item.text}"):
            evidence_numbers.append((number, item.url))

    for claim_number in claim_numbers:
        for evidence_number, url in evidence_numbers:
            if _numbers_match(claim_number, evidence_number):
                matches.append((claim_number, evidence_number, url))
                break
    return matches


def _material_claim_number_items(claim: str) -> list[_ClaimNumber]:
    """Keep strict fact numbers separate from forward-looking context values."""
    items = []
    for value, start, end in extract_substantive_number_spans(claim):
        if _is_asset_label_number(claim, value, start, end):
            continue
        if _is_calendar_date_component_number(claim, value, start, end):
            continue
        if _is_period_marker_number(value):
            continue
        role = "context" if _is_contextual_forward_number(claim, value) else "core"
        items.append(_ClaimNumber(value=value, role=role))
    return items


def _material_claim_numbers(claim: str) -> list[str]:
    """Keep amounts, percentages, and large values; drop period labels like Q1/FY2027."""
    return [item.value for item in _material_claim_number_items(claim)]


def _is_contextual_forward_number(claim: str, value: str) -> bool:
    """Do not let forecast/guidance/target numbers veto reported-fact checks."""
    lower = claim.lower()
    needle = value.lower()
    index = lower.find(needle)
    if index >= 0:
        start = max([0, *[match.end() for match in re.finditer(r"[;,.。；]|(?:\s+(?:and|while|whereas|but)\s+)", lower[:index])]])
        following = lower[index + len(needle) :]
        next_split = re.search(r"[;,.。；]|(?:\s+(?:and|while|whereas|but)\s+)", following)
        end = index + len(needle) + (next_split.start() if next_split else min(len(following), 80))
        window = lower[start:end]
    else:
        compact_needle = re.sub(r"[\s,$]", "", needle)
        compact_claim = re.sub(r"[\s,$]", "", lower)
        index = compact_claim.find(compact_needle)
        if index < 0:
            return False
        window = compact_claim[max(0, index - 80) : index + len(compact_needle) + 80]
    return bool(
        re.search(
            r"\b(expect|expects|expected|forecast|forecasts|project|projected|guidance|outlook|"
            r"estimate|estimates|estimated|target|price target|consensus|will|would|could|should|next quarter|next year)\b",
            window,
        )
    )


def _is_period_marker_number(value: str) -> bool:
    compact = re.sub(r"[\s,$,]", "", value.lower())
    if re.search(r"(%|percent|bps|billion|million|trillion|bn|mn|亿|万|美元)", compact):
        return False
    if "." in compact:
        return False
    try:
        numeric = int(float(compact))
    except ValueError:
        return False
    return 1900 <= numeric <= 2100 or 1 <= numeric <= 4


def _is_calendar_date_component_number(claim: str, value: str, start: int, end: int) -> bool:
    """Drop day/month numbers that are only part of a reporting date."""
    compact = re.sub(r"[\s,$,]", "", value.lower())
    if re.search(r"(%|percent|bps|billion|million|trillion|bn|mn|亿|万|美元)", compact):
        return False
    try:
        numeric = int(float(compact))
    except ValueError:
        return False
    if not 1 <= numeric <= 31:
        return False

    lower = claim.lower()
    left = lower[max(0, start - 24) : start]
    right = lower[end : min(len(lower), end + 24)]
    month = (
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    )
    if re.search(rf"\b(?:{month})\s*$", left) and re.match(r"\s*,?\s*(?:19|20)?\d{2}\b", right):
        return True
    if re.match(rf"\s*(?:{month})\b", right):
        return True
    if (left.endswith(("/", "-")) or right.startswith(("/", "-"))) and re.search(r"(?:19|20)\d{2}", left + right):
        return True
    return False


def _is_asset_label_number(claim: str, value: str, start: int, end: int) -> bool:
    """Drop numbers that are part of instrument names, such as S&P 500."""
    scalar = _numeric_scalar(value)
    if not scalar:
        return False
    number, kind = scalar
    if kind != "plain" or int(number) != number:
        return False

    lower = claim.lower()
    left = lower[max(0, start - 36) : start]
    right = lower[end : min(len(lower), end + 36)]
    index_name_before = re.search(
        r"(?:"
        r"s\s*&\s*p|s\s+and\s+p|standard\s*&\s*poor'?s|standard\s+and\s+poor'?s|sp|"
        r"russell|nasdaq|nikkei|ftse|stoxx|euro\s+stoxx|dax|cac|csi|asx|tsx|kospi|"
        r"hang\s+seng|msci|wilshire|smallcap|midcap"
        r")\s*$",
        left,
    )
    if not index_name_before:
        return False
    return bool(
        re.match(
            r"\s*(?:index|composite|average|futures?|etf|fund|of\s+smaller\s+companies)?\b",
            right,
        )
    )


def _numbers_match(left: str, right: str) -> bool:
    if _numeric_forms(left) & _numeric_forms(right):
        return True
    left_value = _numeric_scalar(left)
    right_value = _numeric_scalar(right)
    if not left_value or not right_value:
        return False
    left_number, left_kind = left_value
    right_number, right_kind = right_value
    if "percent" in {left_kind, right_kind} and left_kind != right_kind:
        return False
    if "bps" in {left_kind, right_kind} and left_kind != right_kind:
        return False
    if left_number == right_number:
        return True
    if left_kind == right_kind == "percent":
        pct_point_diff = abs(left_number - right_number)
        return pct_point_diff <= max(0.15, 0.03 * max(abs(left_number), abs(right_number), 1.0))
    if left_kind == right_kind == "bps":
        return abs(left_number - right_number) <= max(1.0, 0.02 * max(abs(left_number), abs(right_number), 1.0))
    scale = max(abs(left_number), abs(right_number), 1.0)
    tolerance = 0.012 if scale >= 1_000_000 else 0.001
    return abs(left_number - right_number) / scale <= tolerance


def _numeric_forms(value: str) -> set[str]:
    """Generate rough comparable forms for numeric strings and units."""
    raw = value.lower().strip()
    compact = re.sub(r"[\s,$,]", "", raw).replace("percent", "%")
    no_unit = re.sub(r"(billion|million|trillion|bn|mn|bps|%|亿美元|万美元|美元|亿|万)$", "", compact)
    forms = {compact, no_unit}
    if compact.endswith("%"):
        forms.add(compact[:-1])
    return {form for form in forms if form}


def _numeric_scalar(value: str) -> tuple[float, str] | None:
    compact = re.sub(r"[\s,$,]", "", value.lower()).replace("percent", "%")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", compact)
    if not match:
        return None
    number = float(match.group(0))
    if "%" in compact:
        return number, "percent"
    if "bps" in compact:
        return number, "bps"
    if "trillion" in compact:
        return number * 1_000_000_000_000, "amount"
    if "billion" in compact or "bn" in compact:
        return number * 1_000_000_000, "amount"
    if "million" in compact or "mn" in compact:
        return number * 1_000_000, "amount"
    if "亿" in compact:
        return number * 100_000_000, "amount"
    if "万" in compact:
        return number * 10_000, "amount"
    return number, "plain"


def _source_issues(evidence: list[Evidence]) -> list[str]:
    issues = []
    if len({item.domain for item in evidence}) <= 1:
        issues.append("single_source_domain")
    if max((item.source_authority for item in evidence), default=0.0) < 0.65:
        issues.append("no_high_authority_source")
    if len(evidence) < 2:
        issues.append("single_evidence_item")
    return issues


def _rank_evidence_for_verification(evidence: list[Evidence]) -> list[Evidence]:
    """Put likely relevant evidence first before sending snippets to a judge."""
    return sorted(
        evidence,
        key=lambda item: (
            _price_history_priority(item),
            item.numeric_consistency_score,
            item.support_score,
            item.relevance_score,
            item.source_authority,
            item.recency_score,
        ),
        reverse=True,
    )


def _price_history_priority(item: Evidence) -> float:
    text = f"{item.title}\n{item.text}".lower()
    if "historical prices" in text or "historical daily close prices" in text:
        return 1.0
    if "oscillation_signal" in text:
        return 1.0
    return 0.0


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
