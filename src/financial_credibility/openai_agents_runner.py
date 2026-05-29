"""OpenAI Agent SDK runner for multi-tool financial credibility workflows.

This module replaces the hand-rolled Responses-API loop in multi_tool_agent.py
with the `openai-agents` SDK.  The SDK handles the model ↔ tool call loop;
we wrap each registered tool as a `FunctionTool` and capture every invocation
into the existing `AgentToolCall` trace format so the audit chain is unchanged.

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
from .models import AgentToolCall, to_plain
from .tool_profiles import tool_names_for_profile
from .tool_registry import get_registered_tool
from .tool_runtime import execute_tool


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

    Returns (calls, termination_reason) matching the signature of the existing
    raw-API loops so `multi_tool_agent.py` can swap this in transparently.
    """
    from agents import Agent, Runner, RunConfig, ModelSettings

    calls: list[AgentToolCall] = []
    turn_counter = [0]  # mutable counter shared across closures

    tools = build_openai_function_tools(
        tool_profile=tool_profile,
        config=config,
        calls_accumulator=calls,
        turn_counter=turn_counter,
        progress_callback=progress_callback,
    )

    agent = Agent(
        name="CredenceFinancialAgent",
        instructions=instructions,
        tools=tools,
        model=config.openai_model or "gpt-4o-mini",
    )

    user_message = _user_prompt(memo, tickers, as_of_date)

    run_config = RunConfig(
        model_settings=ModelSettings(
            temperature=0.1,
            tool_choice="auto",
            parallel_tool_calls=True,
        ),
        tracing_disabled=True,
    )

    try:
        result = asyncio.run(
            Runner.run(
                agent,
                user_message,
                max_turns=max_steps,
                run_config=run_config,
            )
        )
        # `result` is a RunResult; the SDK stopped the loop
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
