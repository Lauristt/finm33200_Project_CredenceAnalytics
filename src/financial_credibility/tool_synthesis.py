"""Self-extending tool synthesis for CredenceAnalytics.

When the agent calls request_new_tool, this module:
1. Reads the appropriate source description playbook (source_descriptions/*.md)
2. Asks the LLM to write a Python executor function
3. Validates the generated code via exec()
4. Registers the new tool dynamically in tool_registry + tool_runtime
5. Persists to generated_tools.json for survival across restarts

The approach is intentionally minimal: generated executors are standalone
functions using only stdlib (urllib.request, json, datetime). No third-party
imports — the same constraint as the existing data_sources.py adapters.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
import urllib.request
from dataclasses import dataclass, field
from typing import Any

SOURCE_DESCRIPTIONS_DIR = pathlib.Path(__file__).parent / "source_descriptions"
GENERATED_TOOLS_JSON = pathlib.Path(__file__).parent / "generated_tools.json"

# ── Public API ────────────────────────────────────────────────────────────────


@dataclass
class SynthesisResult:
    success: bool
    tool_name: str
    message: str
    executor_code: str = ""
    tool_meta: dict = field(default_factory=dict)


def list_source_descriptions() -> list[str]:
    """Return available source names (without .md extension)."""
    if not SOURCE_DESCRIPTIONS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SOURCE_DESCRIPTIONS_DIR.glob("*.md"))


def read_source_description(name: str) -> str:
    """Read a source playbook by name. Tries partial match if exact name not found."""
    path = SOURCE_DESCRIPTIONS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Partial match
    matches = [p for p in SOURCE_DESCRIPTIONS_DIR.glob("*.md") if name.lower() in p.stem.lower()]
    if matches:
        return matches[0].read_text(encoding="utf-8")
    available = list_source_descriptions()
    raise FileNotFoundError(
        f"Source description '{name}' not found. Available: {', '.join(available)}"
    )


def synthesize_and_register(
    requested_tool_name: str,
    gap_description: str,
    source_doc: str,
    example_query: str,
    config: Any,
    progress_callback: Any = None,
) -> SynthesisResult:
    """
    Full synthesis pipeline: LLM writes executor → validate → register → persist.

    Returns SynthesisResult with success=True if the tool is ready to use.
    """
    if not config.openai_api_key:
        return SynthesisResult(
            success=False,
            tool_name=requested_tool_name,
            message="No OpenAI API key — cannot synthesize tools.",
        )

    _emit(progress_callback, "synthesis_start", "running",
          f"Synthesizing tool '{requested_tool_name}' from '{source_doc}' playbook.")

    # 1. Read the source playbook
    try:
        doc_content = read_source_description(source_doc)
    except FileNotFoundError as exc:
        return SynthesisResult(success=False, tool_name=requested_tool_name, message=str(exc))

    # 2. Ask the LLM to generate executor code + metadata
    llm_result = _call_synthesis_llm(
        tool_name=requested_tool_name,
        gap_description=gap_description,
        source_doc=source_doc,
        doc_content=doc_content,
        example_query=example_query,
        config=config,
    )
    if not llm_result.success:
        _emit(progress_callback, "synthesis_llm", "error", llm_result.message)
        return llm_result

    _emit(progress_callback, "synthesis_llm", "ok",
          f"LLM generated executor for '{requested_tool_name}'.")

    # 3. Validate via exec
    validated = _validate_executor(llm_result.tool_name, llm_result.executor_code)
    if not validated["ok"]:
        msg = f"Validation failed: {validated['error']}"
        _emit(progress_callback, "synthesis_validate", "error", msg)
        return SynthesisResult(success=False, tool_name=requested_tool_name, message=msg)

    # 4. Register in memory (immediately usable)
    _register_in_memory(llm_result.tool_name, validated["fn"], llm_result.tool_meta)

    # 5. Persist to generated_tools.json
    _persist(llm_result.tool_name, llm_result.executor_code, llm_result.tool_meta)

    _emit(progress_callback, "synthesis_done", "ok",
          f"Tool '{llm_result.tool_name}' synthesized, registered, and persisted.")

    return SynthesisResult(
        success=True,
        tool_name=llm_result.tool_name,
        message=f"Tool '{llm_result.tool_name}' is now available.",
        executor_code=llm_result.executor_code,
        tool_meta=llm_result.tool_meta,
    )


def load_persisted_tools() -> int:
    """
    Load previously synthesized tools from generated_tools.json.

    Called at agent startup so tools persist across process restarts.
    Returns the number of tools loaded.
    """
    if not GENERATED_TOOLS_JSON.exists():
        return 0
    try:
        records: list[dict] = json.loads(GENERATED_TOOLS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    count = 0
    for record in records:
        tool_name = record.get("tool_name", "")
        executor_code = record.get("executor_code", "")
        tool_meta = record.get("tool_meta", {})
        if not tool_name or not executor_code:
            continue
        validated = _validate_executor(tool_name, executor_code)
        if not validated["ok"]:
            continue
        _register_in_memory(tool_name, validated["fn"], tool_meta)
        count += 1
    return count


# ── Private helpers ───────────────────────────────────────────────────────────


_SYNTHESIS_SYSTEM_PROMPT = textwrap.dedent("""
    You are a code-generation agent for CredenceAnalytics, a financial claim
    verification system. You generate Python tool executors that fetch data from
    external financial APIs using only the Python standard library.

    Rules for the executor function:
    - Function signature: def execute_{tool_name}(args: dict, config) -> dict
    - Use ONLY stdlib: urllib.request, json, datetime, hashlib, os.
    - Access config attributes safely: getattr(config, 'fred_api_key', None), etc.
    - Available config attributes: openai_api_key, fred_api_key, fmp_api_key,
      alpha_vantage_api_key, finnhub_api_key, bls_api_key, bea_api_key,
      eia_api_key, cftc_app_token, sec_user_agent, serper_api_key.
    - Return a plain dict with the fetched data plus "source" and "url" keys.
    - Handle HTTP errors: catch urllib.error.HTTPError and return
      {"error": str(exc), "source": "<source_id>"}.
    - Set User-Agent header on all SEC requests using config.sec_user_agent or
      "CredenceAnalytics/1.0 (research@example.com)".
    - The function must be complete, runnable, and have no dependencies beyond stdlib.
    - Do NOT use the requests library or any external package.

    Output format — return a JSON object with exactly two keys:
    {
      "executor_code": "<complete Python function as a string>",
      "tool_meta": {
        "tool_name": "<tool_name>",
        "description": "<what this tool does>",
        "when_to_use": "<decision guidance for LLM agent>",
        "data_sources": ["<source_id>"],
        "requires_keys": ["<env_var_name>"],
        "limitations": ["<limitation description>"],
        "input_schema": {
          "type": "object",
          "properties": { ... },
          "required": [...],
          "additionalProperties": false
        },
        "output_schema": {"type": "object"}
      }
    }
""").strip()


def _call_synthesis_llm(
    tool_name: str,
    gap_description: str,
    source_doc: str,
    doc_content: str,
    example_query: str,
    config: Any,
) -> SynthesisResult:
    """Ask the LLM to generate executor code + metadata for a new tool."""
    user_prompt = (
        f"Synthesize a new CredenceAnalytics tool executor.\n\n"
        f"Tool name: {tool_name}\n"
        f"Gap (what the agent couldn't do): {gap_description}\n"
        f"Example query: {example_query}\n\n"
        f"Use this data source playbook:\n"
        f"=== SOURCE: {source_doc} ===\n"
        f"{doc_content}\n"
        f"=== END SOURCE ===\n\n"
        f"Generate the executor function and metadata JSON now."
    )

    body = json.dumps({
        "model": config.openai_model or "gpt-4o-mini",
        "input": [
            {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "text": {"format": {"type": "json_object"}},
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.openai_api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            response = json.loads(resp.read())
    except Exception as exc:
        return SynthesisResult(
            success=False, tool_name=tool_name, message=f"LLM synthesis call failed: {exc}"
        )

    # Extract text from Responses API output
    text = ""
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    break

    if not text:
        return SynthesisResult(
            success=False, tool_name=tool_name, message="LLM returned empty output"
        )

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return SynthesisResult(
            success=False, tool_name=tool_name, message=f"LLM output is not valid JSON: {exc}"
        )

    executor_code = parsed.get("executor_code", "")
    tool_meta = parsed.get("tool_meta", {})

    if not executor_code:
        return SynthesisResult(
            success=False, tool_name=tool_name, message="LLM did not return executor_code"
        )

    tool_meta["tool_name"] = tool_name
    tool_meta["executor_name"] = f"execute_{tool_name}"

    return SynthesisResult(
        success=True,
        tool_name=tool_name,
        message="LLM synthesis complete",
        executor_code=executor_code,
        tool_meta=tool_meta,
    )


def _validate_executor(tool_name: str, code: str) -> dict[str, Any]:
    """Exec the generated code and verify the expected function is defined and callable."""
    ns: dict[str, Any] = {}
    try:
        exec(compile(code, f"<synthesized:{tool_name}>", "exec"), ns)  # noqa: S102
    except SyntaxError as exc:
        return {"ok": False, "error": f"SyntaxError: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"Exec error: {exc}"}

    fn_name = f"execute_{tool_name}"
    fn = ns.get(fn_name)
    if fn is None:
        return {"ok": False, "error": f"Function '{fn_name}' not defined in generated code"}
    if not callable(fn):
        return {"ok": False, "error": f"'{fn_name}' is not callable"}

    return {"ok": True, "fn": fn}


def _register_in_memory(tool_name: str, fn: Any, meta: dict) -> None:
    """Patch tool_registry and tool_runtime so the new tool is immediately usable."""
    from .tool_registry import RegisteredTool, register_dynamic_tool
    from .tool_runtime import register_dynamic_executor

    input_schema = meta.get("input_schema") or {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    registered = RegisteredTool(
        name=tool_name,
        description=meta.get("description", f"Synthesized tool: {tool_name}"),
        input_schema=input_schema,
        output_schema=meta.get("output_schema") or {"type": "object"},
        when_to_use=meta.get("when_to_use", "When this specific external data is needed."),
        data_sources=meta.get("data_sources") or [],
        requires_keys=meta.get("requires_keys") or [],
        limitations=meta.get("limitations") or [],
    )
    register_dynamic_tool(registered)

    captured_fn = fn

    def _executor(args: dict, config: Any) -> dict:
        return captured_fn(args, config)

    register_dynamic_executor(tool_name, _executor)


def _persist(tool_name: str, executor_code: str, tool_meta: dict) -> None:
    """Append a synthesized tool record to generated_tools.json."""
    records: list[dict] = []
    if GENERATED_TOOLS_JSON.exists():
        try:
            records = json.loads(GENERATED_TOOLS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            records = []

    # Deduplicate by tool_name
    records = [r for r in records if r.get("tool_name") != tool_name]
    records.append({
        "tool_name": tool_name,
        "executor_code": executor_code,
        "tool_meta": tool_meta,
    })

    GENERATED_TOOLS_JSON.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _emit(callback: Any, step: str, status: str, summary: str) -> None:
    if callback:
        callback({"step": step, "status": status, "summary": summary, "inputs": {}, "outputs": {}})
