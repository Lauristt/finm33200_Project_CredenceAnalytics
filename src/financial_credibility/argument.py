"""Rule-based claim classifier used to choose scoring rubrics.

This classifier is intentionally lightweight and deterministic. It does not try
to fully understand the claim; it only routes the claim to the right rubric and
records signals that explain the routing decision.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .models import ArgumentType, Classification


PATTERNS: dict[ArgumentType, list[tuple[str, str]]] = {
    ArgumentType.FORECAST: [
        ("future marker", r"\b(will|would|could|should|next quarter|next year|by 20\d{2}|future)\b"),
        ("forecast word", r"\b(expect|expects|expected|forecast|project|projected|guidance|outlook|estimate|estimates)\b"),
    ],
    ArgumentType.ATTRIBUTION_FACT: [
        ("attribution phrase", r"\b(said|says|according to|reported by|cited by|wrote|stated)\b"),
        ("analyst action", r"\b(downgraded|upgraded|initiated|reiterated|price target|rating|analyst)\b"),
    ],
    ArgumentType.METRIC_FACT: [
        ("financial metric", r"\b(revenue|sales|eps|earnings|margin|net income|cash flow|ebitda|free cash flow)\b"),
        ("valuation metric", r"\b(p\/e|pe ratio|market cap|dividend yield|gross margin|operating margin)\b"),
        ("numeric change", r"[-+]?\$?\d[\d,.]*\s*(%|percent|bps|billion|million|trillion|bn|mn)?"),
        ("reported period", r"\b(q[1-4]|quarter|fiscal|fy20\d{2}|year over year|yoy)\b"),
    ],
    ArgumentType.EVENT_FACT: [
        ("company event", r"\b(announced|acquired|merged|launched|approved|filed|settled|sued|investigation)\b"),
        ("capital action", r"\b(buyback|repurchase|dividend|split|offering|ipo|spin[- ]?off)\b"),
        ("labor event", r"\b(layoff|layoffs|hiring|strike)\b"),
    ],
    ArgumentType.OPINION_ANALYSIS: [
        ("valuation opinion", r"\b(overvalued|undervalued|cheap|expensive|fairly valued)\b"),
        ("investment stance", r"\b(bullish|bearish|neutral|buy|sell|hold|attractive|risky)\b"),
        ("business judgment", r"\b(moat|competitive advantage|risk|quality|weak|strong)\b"),
        ("price action pattern", r"\b(oscillat\w*|fluctuat\w*|volatile|volatility|range[- ]?bound|choppy|sideways|swing\w*|trend\w*)\b"),
        ("tentative interpretation", r"\b(seems|appears|looks like|suggests)\b"),
    ],
}

BASE_PRIORITY = {
    ArgumentType.FORECAST: 0.08,
    ArgumentType.METRIC_FACT: 0.06,
    ArgumentType.ATTRIBUTION_FACT: 0.05,
    ArgumentType.EVENT_FACT: 0.04,
    ArgumentType.OPINION_ANALYSIS: 0.03,
}


def classify_argument_type(claim: str) -> Classification:
    """Classify a claim into the argument type used by retrieval and scoring."""
    text = claim.strip().lower()
    scores: dict[ArgumentType, float] = defaultdict(float)
    signals: dict[ArgumentType, list[str]] = defaultdict(list)

    for argument_type, patterns in PATTERNS.items():
        for label, pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                scores[argument_type] += 1.0
                signals[argument_type].append(label)

    if scores[ArgumentType.FORECAST] > 0 and (
        scores[ArgumentType.METRIC_FACT] > 0 or scores[ArgumentType.OPINION_ANALYSIS] > 0
    ):
        scores[ArgumentType.FORECAST] += 1.0
        signals[ArgumentType.FORECAST].append("forward-looking financial claim")

    if not scores:
        return Classification(
            argument_type=ArgumentType.OPINION_ANALYSIS,
            confidence=0.35,
            signals=["fallback: no strong factual or forecast markers"],
            needs_decomposition=_needs_decomposition(claim),
        )

    ranked = sorted(
        scores.items(),
        key=lambda item: (item[1] + BASE_PRIORITY[item[0]], BASE_PRIORITY[item[0]]),
        reverse=True,
    )
    best_type, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = max(0.0, best_score - second_score)
    confidence = min(0.95, 0.45 + 0.13 * best_score + 0.08 * margin)

    return Classification(
        argument_type=best_type,
        confidence=round(confidence, 3),
        signals=signals[best_type],
        needs_decomposition=_needs_decomposition(claim),
    )


def _needs_decomposition(claim: str) -> bool:
    """Detect claims that probably contain multiple subclaims."""
    text = claim.strip()
    if len(text) > 220:
        return True
    if text.count(".") > 1 or text.count(";") > 0:
        return True
    lower = text.lower()
    return bool(re.search(r"\b(and|while|but|although)\b", lower)) and len(text) > 120
