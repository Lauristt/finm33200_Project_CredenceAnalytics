from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
from typing import Any


class ArgumentType(str, Enum):
    METRIC_FACT = "metric_fact"
    EVENT_FACT = "event_fact"
    ATTRIBUTION_FACT = "attribution_fact"
    OPINION_ANALYSIS = "opinion_analysis"
    FORECAST = "forecast"


class SourceType(str, Enum):
    SEC_FILING = "sec_filing"
    COMPANY_IR = "company_ir"
    REGULATOR_EXCHANGE = "regulator_exchange"
    FINANCIAL_MEDIA = "financial_media"
    DATA_VENDOR = "data_vendor"
    ANALYST_RESEARCH = "analyst_research"
    BLOG_NEWSLETTER = "blog_newsletter"
    SOCIAL_FORUM = "social_forum"
    UNKNOWN = "unknown"


class SourceTier(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"


class SupportLabel(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NOT_ENOUGH_INFO = "not_enough_info"


class Verdict(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    INSUFFICIENT = "insufficient"


class CredibilityLabel(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CONTRADICTED_FACT = "contradicted_fact"

    @property
    def zh(self) -> str:
        return {
            CredibilityLabel.VERY_HIGH: "极高",
            CredibilityLabel.HIGH: "高",
            CredibilityLabel.MEDIUM: "中",
            CredibilityLabel.LOW: "较低",
            CredibilityLabel.CONTRADICTED_FACT: "不符合客观事实",
        }[self]


class VerificationVerdict(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    NOT_FOUND = "not_found"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT = "insufficient"
    WEAK = "weak"


@dataclass(frozen=True)
class Classification:
    argument_type: ArgumentType
    confidence: float
    signals: list[str] = field(default_factory=list)
    needs_decomposition: bool = False


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None
    source: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceAssessment:
    source_type: SourceType
    source_tier: SourceTier
    authority_score: float
    domain: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    url: str
    title: str
    text: str
    source_type: SourceType
    source_tier: SourceTier
    domain: str
    published_at: str | None = None
    source_authority: float = 0.0
    recency_score: float = 0.0
    relevance_score: float = 0.0
    entity_match_score: float = 0.0
    numeric_consistency_score: float = 0.0
    support_label: SupportLabel = SupportLabel.NOT_ENOUGH_INFO
    support_score: float = 0.0
    reasoning_quality_score: float = 0.0
    independence_score: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScoreBreakdown:
    source_authority: float
    recency: float
    evidence_support: float
    numeric_consistency: float
    independence: float
    reasoning_quality: float
    penalties: float
    final_score: float
    weights: dict[str, float]


@dataclass(frozen=True)
class VerificationCheck:
    check_type: str
    verdict: str
    confidence: float
    summary: str
    evidence_urls: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    method: str = "heuristic"


@dataclass(frozen=True)
class OverallConclusion:
    overall_label: str
    final_confidence: float
    numeric_confidence: float
    logic_confidence: float
    source_confidence: float
    summary: str


@dataclass(frozen=True)
class EvidencePack:
    claim: str
    ticker: str
    as_of_date: str
    argument_type: ArgumentType
    classification_confidence: float
    verdict: Verdict
    credibility_label: CredibilityLabel
    credibility_score: float
    score_breakdown: ScoreBreakdown
    numeric_check: VerificationCheck | None = None
    logic_check: VerificationCheck | None = None
    source_check: VerificationCheck | None = None
    overall_conclusion: OverallConclusion | None = None
    evidence: list[Evidence] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    mode: str = "strict"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return to_plain(self)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None

    def to_openai_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_tool_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def today_iso() -> str:
    return date.today().isoformat()


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def to_plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    return value
