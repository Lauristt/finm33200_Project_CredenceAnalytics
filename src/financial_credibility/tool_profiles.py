"""Named tool profiles for multi-tool agents and review workflows."""

from __future__ import annotations

from .models import ToolSpec
from .tool_registry import all_registered_tools, get_registered_tool


CORE_TOOLS = [
    "preprocess_statement",
    "extract_entities",
    "map_asset_sources",
    "load_source_documentation",
    "decompose_claims",
    "select_sources",
    "retrieve_evidence",
    "get_canonical_facts",
    "verify_atomic_claim",
    "verify_numeric_claim",
    "verify_logic_claim",
    "verify_source_quality",
    "aggregate_credibility",
    "build_audit_trace",
]

FINANCIAL_STATEMENT_TOOLS = [
    "get_income_statement",
    "get_balance_sheet",
    "get_cash_flow_statement",
    "get_earnings_history",
    "get_sec_company_facts",
    "get_recent_filings",
    "get_company_fundamentals",
]

TOOL_PROFILES: dict[str, list[str]] = {
    "one_shot": ["build_evidence_pack"],
    "agent_core": CORE_TOOLS,
    "retrieval_deep": CORE_TOOLS
    + [
        "get_sec_company_facts",
        "get_recent_filings",
        "get_historical_prices",
        "compare_stock_performance",
        "get_company_fundamentals",
    ],
    "financial_statements": CORE_TOOLS + FINANCIAL_STATEMENT_TOOLS,
    "audit": ["audit_verification_chain"],
    "review": ["summarize_evidence_pack", "summarize_audit_report", "review_tool_surface"],
}


def tool_profile_names() -> list[str]:
    """Return profile names in stable display order."""
    return list(TOOL_PROFILES)


def tool_names_for_profile(profile: str) -> list[str]:
    """Return registered tool names for a profile."""
    if profile == "all":
        return [tool.name for tool in all_registered_tools()]
    try:
        return list(TOOL_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"Unknown tool profile: {profile}") from exc


def tools_for_profile(profile: str):
    """Return registered tool objects for a profile."""
    return [get_registered_tool(name) for name in tool_names_for_profile(profile)]


def tool_specs_for_profile(profile: str) -> list[ToolSpec]:
    """Return provider-neutral tool specs for a profile."""
    return [tool.to_tool_spec() for tool in tools_for_profile(profile)]
