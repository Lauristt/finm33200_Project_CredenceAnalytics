"""Financial credibility tools for US equity claims.

The public package surface intentionally exports the main toolkit, config, and
JSON-serializable model types used by downstream agent/tool integrations.
"""

from .config import ToolkitConfig
from .models import (
    ArgumentType,
    CredibilityLabel,
    Evidence,
    EvidencePack,
    OverallConclusion,
    SearchResult,
    SupportLabel,
    VerificationCheck,
    VerificationVerdict,
    Verdict,
)
from .tool_registry import RegisteredTool, all_registered_tools, all_tool_specs, get_registered_tool
from .tool_runtime import execute_tool
from .toolkit import FinancialCredibilityToolkit

__all__ = [
    "ArgumentType",
    "CredibilityLabel",
    "Evidence",
    "EvidencePack",
    "FinancialCredibilityToolkit",
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
    "execute_tool",
    "get_registered_tool",
]
