from __future__ import annotations

from .models import ToolSpec


def build_evidence_pack_tool() -> ToolSpec:
    return ToolSpec(
        name="build_evidence_pack",
        description=(
            "Build a transparent credibility assessment for a US equity financial "
            "claim using source-aware evidence, narrow semantic judgments, and "
            "explicit numeric, logic, source, and overall confidence checks."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "Financial claim to check.",
                },
                "ticker": {
                    "type": "string",
                    "description": "US equity ticker symbol, e.g. AAPL.",
                },
                "as_of_date": {
                    "type": "string",
                    "description": "Assessment date in YYYY-MM-DD format.",
                },
                "max_sources": {
                    "type": "integer",
                    "default": 8,
                    "description": "Maximum sources to retrieve and score.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["strict", "agentic"],
                    "default": "agentic",
                },
            },
            "required": ["claim", "ticker"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["supported", "contradicted", "mixed", "insufficient"],
                },
                "credibility_label": {
                    "type": "string",
                    "enum": ["very_high", "high", "medium", "low", "contradicted_fact"],
                },
                "credibility_score": {"type": "number"},
                "score_breakdown": {"type": "object"},
                "numeric_check": {"type": "object"},
                "logic_check": {"type": "object"},
                "source_check": {"type": "object"},
                "overall_conclusion": {"type": "object"},
                "evidence": {"type": "array"},
                "risk_flags": {"type": "array"},
            },
        },
    )


def all_tool_specs() -> list[ToolSpec]:
    return [build_evidence_pack_tool()]
