"""Provider-neutral tool schema adapters for LLM tool calling."""

from __future__ import annotations

from .models import ToolSpec
from .tool_registry import all_tool_specs as registry_tool_specs
from .tool_registry import get_registered_tool


def build_evidence_pack_tool() -> ToolSpec:
    """Return the high-level end-to-end tool spec."""
    return get_registered_tool("build_evidence_pack").to_tool_spec()


def all_tool_specs() -> list[ToolSpec]:
    """Return all provider-neutral tool specs exported by this package."""
    return registry_tool_specs()


def export_openai_tools() -> list[dict]:
    """Return all tools in OpenAI function-tool format."""
    return [spec.to_openai_tool_schema() for spec in all_tool_specs()]


def export_anthropic_tools() -> list[dict]:
    """Return all tools in Anthropic tool-use format."""
    return [spec.to_anthropic_tool_schema() for spec in all_tool_specs()]
