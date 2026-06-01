"""Financial credibility tools for US equity claims.

The public package surface intentionally exports the main toolkit, config, and
JSON-serializable model types used by downstream agent/tool integrations.
"""

from .config import ToolkitConfig
from .entity_extraction import extract_entities_from_memo
from .asset_source_map import asset_source_plan, describe_data_sources, series_mappings_for_claim
from .news_benchmark import benchmark_cases, evaluate_news_benchmark
from .models import (
    ArgumentType,
    AtomicClaim,
    AtomicClaimResult,
    AgentToolCall,
    AgentTrace,
    AuditFinding,
    AuditReport,
    AuditTrace,
    CanonicalFact,
    ConfidenceComponents,
    CredibilityLabel,
    Evidence,
    EvidencePack,
    EntityResolution,
    LicenseTag,
    NumericDerivation,
    OverallConclusion,
    SearchResult,
    SupportLabel,
    VerificationCheck,
    VerificationVerdict,
    Verdict,
)
from .multi_tool_agent import MultiToolAgentRunner
from .tool_registry import RegisteredTool, all_registered_tools, all_tool_specs, get_registered_tool
from .tool_runtime import execute_tool
from .toolkit import FinancialCredibilityToolkit

__all__ = [
    "ArgumentType",
    "AtomicClaim",
    "AtomicClaimResult",
    "AgentToolCall",
    "AgentTrace",
    "AuditFinding",
    "AuditReport",
    "AuditTrace",
    "CanonicalFact",
    "ConfidenceComponents",
    "CredibilityLabel",
    "Evidence",
    "EvidencePack",
    "EntityResolution",
    "FinancialCredibilityToolkit",
    "LicenseTag",
    "MultiToolAgentRunner",
    "NumericDerivation",
    "OverallConclusion",
    "RegisteredTool",
    "SearchResult",
    "SupportLabel",
    "ToolkitConfig",
    "VerificationCheck",
    "VerificationVerdict",
    "Verdict",
    "all_registered_tools",
    "all_tool_specs",
    "asset_source_plan",
    "benchmark_cases",
    "describe_data_sources",
    "evaluate_news_benchmark",
    "execute_tool",
    "extract_entities_from_memo",
    "get_registered_tool",
    "series_mappings_for_claim",
]
