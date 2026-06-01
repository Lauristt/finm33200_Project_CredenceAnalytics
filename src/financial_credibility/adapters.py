"""Provider-neutral tool schema adapters for LLM tool calling."""

from __future__ import annotations

from .models import ToolSpec
from .tool_profiles import tool_specs_for_profile
from .tool_registry import all_tool_specs as registry_tool_specs
from .tool_registry import get_registered_tool


def build_evidence_pack_tool() -> ToolSpec:
    """Return the high-level end-to-end tool spec."""
    return get_registered_tool("build_evidence_pack").to_tool_spec()


def all_tool_specs(profile: str | None = None) -> list[ToolSpec]:
    """Return all provider-neutral tool specs exported by this package."""
    if profile:
        return tool_specs_for_profile(profile)
    return registry_tool_specs()


def export_openai_tools(profile: str | None = None) -> list[dict]:
    """Return all tools in OpenAI function-tool format."""
    return [spec.to_openai_tool_schema() for spec in all_tool_specs(profile)]


def export_openai_response_tools(profile: str | None = None) -> list[dict]:
    """Return tools in the Responses API function format."""
    return [
        {
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.input_schema,
            "strict": False,
        }
        for spec in all_tool_specs(profile)
    ]


def export_anthropic_tools(profile: str | None = None) -> list[dict]:
    """Return all tools in Anthropic tool-use format."""
    return [spec.to_anthropic_tool_schema() for spec in all_tool_specs(profile)]
