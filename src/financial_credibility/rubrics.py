from __future__ import annotations

from .models import ArgumentType


SCORE_FIELDS = [
    "source_authority",
    "recency",
    "evidence_support",
    "numeric_consistency",
    "independence",
    "reasoning_quality",
]


RUBRIC_WEIGHTS: dict[ArgumentType, dict[str, float]] = {
    ArgumentType.METRIC_FACT: {
        "source_authority": 0.25,
        "recency": 0.10,
        "evidence_support": 0.25,
        "numeric_consistency": 0.25,
        "independence": 0.10,
        "reasoning_quality": 0.05,
    },
    ArgumentType.EVENT_FACT: {
        "source_authority": 0.20,
        "recency": 0.20,
        "evidence_support": 0.25,
        "numeric_consistency": 0.10,
        "independence": 0.15,
        "reasoning_quality": 0.10,
    },
    ArgumentType.ATTRIBUTION_FACT: {
        "source_authority": 0.25,
        "recency": 0.15,
        "evidence_support": 0.25,
        "numeric_consistency": 0.10,
        "independence": 0.15,
        "reasoning_quality": 0.10,
    },
    ArgumentType.OPINION_ANALYSIS: {
        "source_authority": 0.10,
        "recency": 0.10,
        "evidence_support": 0.15,
        "numeric_consistency": 0.05,
        "independence": 0.20,
        "reasoning_quality": 0.40,
    },
    ArgumentType.FORECAST: {
        "source_authority": 0.10,
        "recency": 0.10,
        "evidence_support": 0.20,
        "numeric_consistency": 0.05,
        "independence": 0.25,
        "reasoning_quality": 0.30,
    },
}


FACTUAL_TYPES = {
    ArgumentType.METRIC_FACT,
    ArgumentType.EVENT_FACT,
    ArgumentType.ATTRIBUTION_FACT,
}
