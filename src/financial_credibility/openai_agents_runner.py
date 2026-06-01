"""OpenAI Agent SDK runner for multi-tool financial credibility workflows.

This module replaces the hand-rolled Responses-API loop in multi_tool_agent.py
with the `openai-agents` SDK.  The SDK handles the model ↔ tool call loop;
we wrap each registered tool as a `FunctionTool` and capture every invocation
into the existing `AgentToolCall` trace format so the audit chain is unchanged.

Self-extending agent:
  When the agent calls `request_new_tool`, tool_synthesis.py is invoked to
  generate, validate, register, and persist a new tool.  The agent then retries
  the original query with the new tool available (up to MAX_SYNTHESIS_ROUNDS).

Install once:
    pip install "openai-agents>=0.0.1"
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any, Callable

from .config import ToolkitConfig
from .models import AgentToolCall, to_plain  # to_plain used in request_new_tool closure
from .tool_profiles import tool_names_for_profile
from .tool_registry import get_registered_tool
from .tool_runtime import execute_tool


MAX_SYNTHESIS_ROUNDS = 3  # max agent→synthesize→retry cycles per query


def is_available() -> bool:
    """Return True when the openai-agents package can be imported."""
    try:
        import agents  # noqa: F401
        return True
    except ImportError:
        return False


def build_openai_function_tools(
    tool_profile: str,
    config: ToolkitConfig,
    calls_accumulator: list[AgentToolCall],
    turn_counter: list[int],
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> list[Any]:
    """
    Build a list of Agent SDK FunctionTool objects for the given profile.

    Each tool records its invocation into `calls_accumulator` so the existing
    audit / trace infrastructure stays intact.
    """
    from agents import FunctionTool

    tools = []
    for name in tool_names_for_profile(tool_profile):
        try:
            registered = get_registered_tool(name)
        except KeyError:
            continue

        # Capture `name` and `registered` in a closure
        def _make_invoke(tool_name: str, schema: dict[str, Any]):
            # Relax strict mode: our schemas may have `anyOf` or optional
            # fields that strict JSON-schema validation would reject.
            async def on_invoke(ctx: Any, args_json: str) -> str:
                idx = turn_counter[0]
                turn_counter[0] += 1

                try:
                    args: dict[str, Any] = json.loads(args_json) if args_json else {}
                except json.JSONDecodeError:
                    args = {}

                t0 = time.monotonic()
                try:
                    result = execute_tool(tool_name, args, config)
                    status = "ok"
                    error = None
                except Exception as exc:
                    result = {"error": str(exc)}
                    status = "error"
                    error = str(exc)

                duration_ms = int((time.monotonic() - t0) * 1000)
                encoded = json.dumps(
                    to_plain(result), ensure_ascii=False, sort_keys=True, default=str
                )
                event = AgentToolCall(
                    call_id=f"sdk_{idx}_{_sha256(tool_name + encoded)[:8]}",
                    turn_index=idx,
                    tool_name=tool_name,
                    arguments=to_plain(args),
                    status=status,
                    error=error,
                    duration_ms=duration_ms,
                    output_preview=encoded[:800],
                    output_hash=_sha256(encoded),
                )
                calls_accumulator.append(event)

                if progress_callback:
                    progress_callback(
                        {
                            "step": "agent_tool_call",
                            "status": status,
                            "summary": f"{tool_name} executed.",
                            "inputs": {},
                            "outputs": to_plain(event),
                        }
                    )

                return encoded

            return on_invoke

        tool = FunctionTool(
            name=name,
            description=registered.agent_description(),
            params_json_schema=registered.input_schema,
            on_invoke_tool=_make_invoke(name, registered.input_schema),
            strict_json_schema=False,
        )
        tools.append(tool)

    return tools


def run_openai_agents_sdk(
    memo: str,
    tickers: list[str],
    as_of_date: str | None,
    max_steps: int,
    instructions: str,
    tool_profile: str,
    config: ToolkitConfig,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[AgentToolCall], str]:
    """
    Run the credibility agent using the OpenAI Agents SDK.

    Includes a self-extending meta-loop: if the agent calls request_new_tool,
    tool_synthesis.py generates and registers the tool, then the agent retries
    the original query with the new tool available (up to MAX_SYNTHESIS_ROUNDS).

    Returns (calls, termination_reason) matching the signature expected by
    multi_tool_agent.py so the swap is transparent.
    """
    # Load any tools synthesized in previous sessions
    from .tool_synthesis import load_persisted_tools
    load_persisted_tools()

    all_calls: list[AgentToolCall] = []
    termination_reason = "final"

    for _round in range(MAX_SYNTHESIS_ROUNDS):
        synthesis_requests: list[dict[str, Any]] = []
        round_calls, reason = _run_sdk_once(
            memo=memo,
            tickers=tickers,
            as_of_date=as_of_date,
            max_steps=max_steps,
            instructions=instructions,
            tool_profile=tool_profile,
            config=config,
            progress_callback=progress_callback,
            synthesis_requests=synthesis_requests,
        )
        all_calls.extend(round_calls)
        termination_reason = reason

        if not synthesis_requests:
            break  # Normal completion — no synthesis requested

        # Synthesize each requested tool, then retry if any succeed
        from .tool_synthesis import synthesize_and_register, list_source_descriptions
        synthesized_any = False
        for req in synthesis_requests:
            tool_name = req.get("requested_tool_name", "").strip()
            source_doc = req.get("source_doc", "").strip()
            gap = req.get("gap_description", "")
            query = req.get("example_query", memo)

            if not tool_name or not source_doc:
                continue

            result = synthesize_and_register(
                requested_tool_name=tool_name,
                gap_description=gap,
                source_doc=source_doc,
                example_query=query,
                config=config,
                progress_callback=progress_callback,
            )
            if result.success:
                synthesized_any = True
            else:
                if progress_callback:
                    progress_callback({
                        "step": "synthesis_failed",
                        "status": "error",
                        "summary": f"Tool synthesis failed for '{tool_name}': {result.message}",
                        "inputs": {},
                        "outputs": {},
                    })

        if not synthesized_any:
            break  # Synthesis failed on all requests — stop retrying

        # Loop continues: retry the original query with new tools registered

    return all_calls, termination_reason


def _run_sdk_once(
    memo: str,
    tickers: list[str],
    as_of_date: str | None,
    max_steps: int,
    instructions: str,
    tool_profile: str,
    config: ToolkitConfig,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    synthesis_requests: list[dict[str, Any]],
) -> tuple[list[AgentToolCall], str]:
    """Run one pass of the SDK agent loop and collect synthesis requests."""
    from agents import Agent, Runner, RunConfig, ModelSettings

    calls: list[AgentToolCall] = []
    turn_counter = [0]

    tools = build_openai_function_tools(
        tool_profile=tool_profile,
        config=config,
        calls_accumulator=calls,
        turn_counter=turn_counter,
        progress_callback=progress_callback,
    )

    # Always append the request_new_tool meta-tool regardless of profile
    tools.append(_make_request_new_tool(synthesis_requests, calls, turn_counter, progress_callback))

    agent = Agent(
        name="CredenceFinancialAgent",
        instructions=instructions,
        tools=tools,
        model=config.openai_model or "gpt-4o-mini",
    )

    run_config = RunConfig(
        model_settings=ModelSettings(
            temperature=0.1,
            tool_choice="auto",
            parallel_tool_calls=True,
        ),
        tracing_disabled=True,
    )

    try:
        asyncio.run(
            Runner.run(
                agent,
                _user_prompt(memo, tickers, as_of_date),
                max_turns=max_steps,
                run_config=run_config,
            )
        )
        termination_reason = "final"
    except Exception as exc:
        calls.append(
            AgentToolCall(
                call_id=f"sdk_error_{len(calls)}",
                turn_index=len(calls),
                tool_name="agent_model_loop",
                arguments={},
                status="error",
                error=str(exc),
                output_preview="",
                output_hash="",
            )
        )
        termination_reason = "tool_error"

    return calls, termination_reason


def _make_request_new_tool(
    synthesis_requests: list[dict[str, Any]],
    calls_accumulator: list[AgentToolCall],
    turn_counter: list[int],
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> Any:
    """Build the request_new_tool FunctionTool that triggers the synthesis pipeline."""
    from agents import FunctionTool
    from .tool_synthesis import list_source_descriptions

    available_sources = list_source_descriptions()

    async def on_invoke(ctx: Any, args_json: str) -> str:
        try:
            args: dict[str, Any] = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError:
            args = {}

        idx = turn_counter[0]
        turn_counter[0] += 1

        tool_name = args.get("requested_tool_name", "")
        source_doc = args.get("source_doc", "")
        gap = args.get("gap_description", "")

        synthesis_requests.append(args)

        result_payload = {
            "status": "synthesis_queued",
            "requested_tool_name": tool_name,
            "source_doc": source_doc,
            "message": (
                f"Tool '{tool_name}' synthesis queued from source '{source_doc}'. "
                "The system will generate and register it, then retry your query."
            ),
        }
        encoded = json.dumps(result_payload)
        event = AgentToolCall(
            call_id=f"sdk_{idx}_synth_{_sha256(tool_name + source_doc)[:8]}",
            turn_index=idx,
            tool_name="request_new_tool",
            arguments=to_plain(args),
            status="ok",
            duration_ms=0,
            output_preview=encoded[:800],
            output_hash=_sha256(encoded),
        )
        calls_accumulator.append(event)

        if progress_callback:
            progress_callback({
                "step": "synthesis_requested",
                "status": "running",
                "summary": f"Agent requested tool synthesis: '{tool_name}' from '{source_doc}'.",
                "inputs": {},
                "outputs": to_plain(event),
            })

        return encoded

    return FunctionTool(
        name="request_new_tool",
        description=(
            "Request synthesis of a brand-new tool when NONE of the available tools "
            "can fetch the specific data you need. The system will read the data source "
            f"playbook, write a Python executor, validate it, register it, and retry "
            f"your query automatically. Available source docs: {', '.join(available_sources)}. "
            "Use this as a LAST RESORT only — prefer existing tools first."
        ),
        params_json_schema={
            "type": "object",
            "properties": {
                "requested_tool_name": {
                    "type": "string",
                    "description": "snake_case name for the new tool, e.g. get_bls_cpi_series",
                },
                "gap_description": {
                    "type": "string",
                    "description": "Precise description of what capability is missing and why existing tools cannot serve it.",
                },
                "source_doc": {
                    "type": "string",
                    "description": f"Name of the source description to use (without .md). One of: {', '.join(available_sources)}",
                },
                "example_query": {
                    "type": "string",
                    "description": "Concrete example of what you are trying to fetch, e.g. 'BLS CPI for 2024-12'.",
                },
            },
            "required": ["requested_tool_name", "gap_description", "source_doc", "example_query"],
            "additionalProperties": False,
        },
        on_invoke_tool=on_invoke,
        strict_json_schema=False,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_prompt(memo: str, tickers: list[str], as_of_date: str | None) -> str:
    return json.dumps(
        {
            "task": "verify_financial_claims",
            "memo": memo,
            "tickers": tickers,
            "as_of_date": as_of_date,
            "instruction": (
                "Call tools as needed. Stop when you have enough evidence "
                "to produce a concise final assessment."
            ),
        },
        ensure_ascii=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
