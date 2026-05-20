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
from .toolkit import FinancialCredibilityToolkit

__all__ = [
    "ArgumentType",
    "CredibilityLabel",
    "Evidence",
    "EvidencePack",
    "FinancialCredibilityToolkit",
    "OverallConclusion",
    "SearchResult",
    "SupportLabel",
    "ToolkitConfig",
    "VerificationCheck",
    "VerificationVerdict",
    "Verdict",
]
