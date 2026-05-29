"""Repo-native multi-tool agent runner with trace capture.

OpenAI path preference (highest → lowest priority):
  1. openai-agents SDK  – full agentic loop, auto tool-choice (requires pip install openai-agents)
  2. Responses API loop – raw HTTP fallback when SDK not installed
  3. Deterministic fallback – when no LLM provider is configured
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import replace
from typing import Any, Callable

from .adapters import export_anthropic_tools, export_openai_response_tools
from .audit_agent import audit_verification_chain
from .config import ToolkitConfig
from .models import AgentToolCall, AgentTrace, to_plain
from .preprocessing import preprocess_statement
from .rubrics import FACTUAL_TYPES
from .time_context import infer_time_context
from .tool_profiles import tool_names_for_profile
from .tool_runtime import execute_tool


DEFAULT_MAX_STEPS = 20


class MultiToolAgentRunner:
    """Run a model-selected multi-tool workflow and return a report payload."""

    def __init__(
        self,
        config: ToolkitConfig | None = None,
        tool_executor=execute_tool,
    ):
        self.config = config or ToolkitConfig.from_env()
        self.tool_executor = tool_executor

    def run(
        self,
        memo: str,
        tickers: list[str] | None = None,
        as_of_date: str | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        tool_profile: str = "agent_core",
        provider: str = "auto",
        audit: bool = True,
        prefetched_results: list[dict[str, Any]] | None = None,
        source_results: list[dict[str, Any]] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run a multi-tool agent, then attach trace and audit output to a report."""
        original_memo = memo
        if max_steps == DEFAULT_MAX_STEPS:
            max_steps = max(DEFAULT_MAX_STEPS, len(tickers or []) * 5)
        preprocessed = preprocess_statement(memo)
        memo = preprocessed.clean_text
        time_context = infer_time_context(memo, as_of_date)
        effective_as_of_date = time_context.effective_as_of_date or as_of_date
        selected_provider, model = self._select_provider(provider)
        run_id = _run_id(memo, tickers or [], effective_as_of_date, tool_profile)
        instructions = _agent_instructions(tool_profile)
        trace = AgentTrace.create(
            run_id=run_id,
            provider=selected_provider,
            model=model,
            tool_profile=tool_profile,
            instructions_hash=_sha256(instructions),
            notes=[],
        )
        _emit(
            progress_callback,
            "preprocess_statement",
            "ok" if preprocessed.changed else "unchanged",
            "Removed copied-page boilerplate before agent planning." if preprocessed.changed else "Input did not require preprocessing.",
            outputs=preprocessed.to_dict(),
        )
        _emit(
            progress_callback,
            "agent_start",
            "running",
            f"Starting multi-tool agent with profile {tool_profile}.",
            outputs={"provider": selected_provider, "model": model, "tool_profile": tool_profile},
        )

        if selected_provider == "none":
            trace = self._run_deterministic_fallback(
                trace=trace,
                memo=memo,
                tickers=tickers or [],
                as_of_date=effective_as_of_date,
                max_steps=max_steps,
                tool_profile=tool_profile,
                prefetched_results=prefetched_results,
                source_results=source_results,
                progress_callback=progress_callback,
            )
        else:
            trace = self._run_model_loop(
                trace=trace,
                memo=memo,
                tickers=tickers or [],
                as_of_date=effective_as_of_date,
                max_steps=max_steps,
                provider=selected_provider,
                model=model or "",
                instructions=instructions,
                tool_profile=tool_profile,
                prefetched_results=prefetched_results,
                source_results=source_results,
                progress_callback=progress_callback,
            )

        payload = self._build_compatible_report(
            memo=memo,
            tickers=tickers or [],
            as_of_date=effective_as_of_date,
            prefetched_results=prefetched_results,
            source_results=source_results,
            progress_callback=progress_callback,
        )
        payload.setdefault("input", {})["mode"] = "multi_tool"
        payload["input"]["original_memo"] = original_memo
        payload["input"]["memo"] = memo
        payload["input"]["preprocessing"] = preprocessed.to_dict()
        payload["input"]["requested_as_of_date"] = as_of_date
        payload["input"]["time_context"] = time_context.to_dict()
        payload["input"]["tool_profile"] = tool_profile
        payload["input"]["agent_max_steps"] = max_steps
        payload["agent_trace"] = to_plain(trace)
        payload.setdefault("summary", {})["agent_tool_call_count"] = len(trace.tool_calls)
        payload["summary"]["agent_termination_reason"] = trace.termination_reason
        if audit:
            audit_report = audit_verification_chain(
                report_payload=payload,
                agent_trace=trace,
                config=self.config,
            )
            payload["audit_report"] = to_plain(audit_report)
            for finding in audit_report.findings:
                _emit(
                    progress_callback,
                    "audit_finding",
                    finding.severity,
                    finding.summary,
                    outputs=to_plain(finding),
                )
        from .reporting import render_markdown_report

        payload["report_markdown"] = render_markdown_report(payload)
        _emit(
            progress_callback,
            "agent_finish",
            "ok",
            f"Finished multi-tool agent with {len(trace.tool_calls)} tool call(s).",
            outputs={"termination_reason": trace.termination_reason},
        )
        return payload

    def _select_provider(self, requested: str) -> tuple[str, str | None]:
        requested = (requested or "auto").lower()
        if requested in {"openai", "auto"} and self.config.openai_api_key and self.config.openai_model:
            return "openai", self.config.openai_model
        if requested in {"anthropic", "auto"} and self.config.anthropic_api_key and self.config.anthropic_model:
            return "anthropic", self.config.anthropic_model
        if requested not in {"auto", "none"}:
            return "none", None
        return "none", None

    def _run_deterministic_fallback(
        self,
        trace: AgentTrace,
        memo: str,
        tickers: list[str],
        as_of_date: str | None,
        max_steps: int,
        tool_profile: str,
        prefetched_results: list[dict[str, Any]] | None,
        source_results: list[dict[str, Any]] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> AgentTrace:
        calls: list[AgentToolCall] = []
        allowed_tools = set(tool_names_for_profile(tool_profile))

        def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name not in allowed_tools:
                return {}
            if len(calls) >= max_steps:
                return {}
            result, event = self._execute_traced_tool(name, args, len(calls), "fallback")
            calls.append(event)
            _emit(progress_callback, "agent_tool_call", event.status, f"{name} executed.", outputs=to_plain(event))
            return result

        entities = call("extract_entities", {"memo": memo})
        claims = call("decompose_claims", {"claim": memo})
        clean_tickers = tickers or _entity_targets(entities)
        claim_text = _first_fact_checkable_claim_text(claims)
        if "build_evidence_pack" in allowed_tools and clean_tickers:
            call(
                "build_evidence_pack",
                {
                    "claim": claim_text or memo,
                    "ticker": str(clean_tickers[0]),
                    "as_of_date": as_of_date,
                    "prefetched_results": prefetched_results,
                    "source_results": source_results,
                },
            )
            reason = "max_steps" if len(calls) >= max_steps else "no_provider_fallback"
            return replace(trace, tool_calls=calls, termination_reason=reason, notes=trace.notes + ["Used deterministic fallback because no configured LLM provider was available."])
        if not claim_text:
            reason = "max_steps" if len(calls) >= max_steps else "no_provider_fallback"
            return replace(
                trace,
                tool_calls=calls,
                termination_reason=reason,
                notes=trace.notes
                + [
                    "Used deterministic fallback because no configured LLM provider was available.",
                    "Skipped retrieval and verification because every decomposed claim was forecast/opinion/non-factual, including vague non-falsifiable commentary such as priced in or another beat.",
                ],
            )
        selected_sources: list[str] | None = None
        if claim_text:
            selection = call("select_sources", {"claim": claim_text})
            selections = selection.get("selections") or []
            if selections:
                selected_sources = selections[0].get("selected_provider_names") or selections[0].get("selected_sources") or []
        if clean_tickers:
            ticker = str(clean_tickers[0])
            retrieved = call(
                "retrieve_evidence",
                {
                    "claim": claim_text,
                    "ticker": ticker,
                    "as_of_date": as_of_date,
                    "selected_sources": selected_sources,
                    "prefetched_results": prefetched_results,
                    "source_results": source_results,
                },
            )
            canonical = call(
                "get_canonical_facts",
                {
                    "ticker": ticker,
                    "evidence": retrieved.get("evidence") or [],
                },
            )
            call(
                "verify_atomic_claim",
                {
                    "claim": claim_text,
                    "ticker": ticker,
                    "evidence": retrieved.get("evidence") or [],
                    "canonical_facts": canonical.get("canonical_facts") or [],
                },
            )
            call(
                "build_audit_trace",
                {
                    "claim": claim_text,
                    "ticker": ticker,
                    "as_of_date": as_of_date,
                    "evidence": retrieved.get("evidence") or [],
                    "canonical_facts": canonical.get("canonical_facts") or [],
                },
            )
        reason = "max_steps" if len(calls) >= max_steps else "no_provider_fallback"
        return replace(trace, tool_calls=calls, termination_reason=reason, notes=trace.notes + ["Used deterministic fallback because no configured LLM provider was available."])

    def _run_model_loop(
        self,
        trace: AgentTrace,
        memo: str,
        tickers: list[str],
        as_of_date: str | None,
        max_steps: int,
        provider: str,
        model: str,
        instructions: str,
        tool_profile: str,
        prefetched_results: list[dict[str, Any]] | None,
        source_results: list[dict[str, Any]] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> AgentTrace:
        calls: list[AgentToolCall] = []
        repeated: dict[tuple[str, str], int] = {}
        try:
            if provider == "openai":
                calls, reason = self._run_openai_loop(
                    memo, tickers, as_of_date, max_steps, instructions, tool_profile, prefetched_results, source_results, repeated, progress_callback
                )
            else:
                calls, reason = self._run_anthropic_loop(
                    memo, tickers, as_of_date, max_steps, instructions, tool_profile, prefetched_results, source_results, repeated, progress_callback
                )
        except Exception as exc:
            calls.append(
                AgentToolCall(
                    call_id=f"agent_error_{len(calls)}",
                    turn_index=len(calls),
                    tool_name="agent_model_loop",
                    arguments={},
                    status="error",
                    error=str(exc),
                    output_preview="",
                    output_hash="",
                )
            )
            reason = "tool_error"
        return replace(trace, tool_calls=calls, termination_reason=reason)

    def _run_openai_loop(
        self,
        memo: str,
        tickers: list[str],
        as_of_date: str | None,
        max_steps: int,
        instructions: str,
        tool_profile: str,
        prefetched_results: list[dict[str, Any]] | None,
        source_results: list[dict[str, Any]] | None,
        repeated: dict[tuple[str, str], int],
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> tuple[list[AgentToolCall], str]:
        # ── Prefer the OpenAI Agents SDK when installed ───────────────────────
        from .openai_agents_runner import is_available as _sdk_available, run_openai_agents_sdk

        if _sdk_available():
            _emit(
                progress_callback,
                "agent_start",
                "running",
                "Using OpenAI Agents SDK for tool orchestration.",
            )
            return run_openai_agents_sdk(
                memo=memo,
                tickers=tickers,
                as_of_date=as_of_date,
                max_steps=max_steps,
                instructions=instructions,
                tool_profile=tool_profile,
                config=self.config,
                progress_callback=progress_callback,
            )

        # ── Fallback: raw Responses API loop ─────────────────────────────────
        _emit(
            progress_callback,
            "agent_start",
            "running",
            "openai-agents SDK not found; using raw Responses API loop.",
        )
        tools = export_openai_response_tools(tool_profile)
        input_payload: Any = _user_prompt(memo, tickers, as_of_date)
        previous_response_id = None
        calls: list[AgentToolCall] = []
        for turn in range(max_steps):
            body = {
                "model": self.config.openai_model,
                "instructions": instructions,
                "input": input_payload,
                "tools": tools,
                "tool_choice": "auto",
                "parallel_tool_calls": True,
            }
            if previous_response_id:
                body["previous_response_id"] = previous_response_id
            response = self._post_json("https://api.openai.com/v1/responses", body, {"Authorization": f"Bearer {self.config.openai_api_key}"})
            previous_response_id = response.get("id")
            function_calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if not function_calls:
                return calls, "final"
            outputs = []
            for item in function_calls:
                if len(calls) >= max_steps:
                    return calls, "max_steps"
                name = item.get("name", "")
                args = _loads_args(item.get("arguments") or "{}")
                args = _inject_known_args(name, args, as_of_date, prefetched_results, source_results)
                result, event = self._execute_guarded_model_call(name, args, len(calls), repeated)
                calls.append(event)
                _emit(progress_callback, "agent_tool_call", event.status, f"{name} executed.", outputs=to_plain(event))
                if event.status == "repeat_limit":
                    return calls, "repeated_call"
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.get("call_id"),
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
            input_payload = outputs
        return calls, "max_steps"

    def _run_anthropic_loop(
        self,
        memo: str,
        tickers: list[str],
        as_of_date: str | None,
        max_steps: int,
        instructions: str,
        tool_profile: str,
        prefetched_results: list[dict[str, Any]] | None,
        source_results: list[dict[str, Any]] | None,
        repeated: dict[tuple[str, str], int],
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> tuple[list[AgentToolCall], str]:
        tools = export_anthropic_tools(tool_profile)
        messages: list[dict[str, Any]] = [{"role": "user", "content": _user_prompt(memo, tickers, as_of_date)}]
        calls: list[AgentToolCall] = []
        for _turn in range(max_steps):
            body = {
                "model": self.config.anthropic_model,
                "system": instructions,
                "messages": messages,
                "tools": tools,
                "max_tokens": 1200,
            }
            response = self._post_json(
                "https://api.anthropic.com/v1/messages",
                body,
                {
                    "x-api-key": self.config.anthropic_api_key or "",
                    "anthropic-version": "2023-06-01",
                },
            )
            content = response.get("content", [])
            tool_uses = [item for item in content if item.get("type") == "tool_use"]
            if not tool_uses:
                return calls, "final"
            messages.append({"role": "assistant", "content": content})
            tool_results = []
            for item in tool_uses:
                if len(calls) >= max_steps:
                    return calls, "max_steps"
                name = item.get("name", "")
                args = _inject_known_args(name, dict(item.get("input") or {}), as_of_date, prefetched_results, source_results)
                result, event = self._execute_guarded_model_call(name, args, len(calls), repeated)
                calls.append(event)
                _emit(progress_callback, "agent_tool_call", event.status, f"{name} executed.", outputs=to_plain(event))
                if event.status == "repeat_limit":
                    return calls, "repeated_call"
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": item.get("id"),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        return calls, "max_steps"

    def _execute_guarded_model_call(
        self,
        name: str,
        args: dict[str, Any],
        turn_index: int,
        repeated: dict[tuple[str, str], int],
    ) -> tuple[dict[str, Any], AgentToolCall]:
        key = (name, _stable_args(args))
        repeated[key] = repeated.get(key, 0) + 1
        if repeated[key] > 2:
            event = AgentToolCall(
                call_id=f"repeat_{turn_index}",
                turn_index=turn_index,
                tool_name=name,
                arguments=args,
                status="repeat_limit",
                error="Identical tool call repeated more than twice.",
            )
            return {"error": event.error}, event
        return self._execute_traced_tool(name, args, turn_index, "model")

    def _execute_traced_tool(
        self,
        name: str,
        args: dict[str, Any],
        turn_index: int,
        call_prefix: str,
    ) -> tuple[dict[str, Any], AgentToolCall]:
        start = time.monotonic()
        try:
            result = self.tool_executor(name, args, self.config)
            status = "ok"
            error = None
        except Exception as exc:
            result = {"error": str(exc)}
            status = "error"
            error = str(exc)
        duration_ms = int((time.monotonic() - start) * 1000)
        encoded = json.dumps(to_plain(result), ensure_ascii=False, sort_keys=True, default=str)
        event = AgentToolCall(
            call_id=f"{call_prefix}_{turn_index}_{_sha256(name + encoded)[:8]}",
            turn_index=turn_index,
            tool_name=name,
            arguments=to_plain(args),
            status=status,
            error=error,
            duration_ms=duration_ms,
            output_preview=encoded[:800],
            output_hash=_sha256(encoded),
        )
        return result, event

    def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        request_headers = {"Content-Type": "application/json", **headers}
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _build_compatible_report(
        self,
        memo: str,
        tickers: list[str],
        as_of_date: str | None,
        prefetched_results: list[dict[str, Any]] | None,
        source_results: list[dict[str, Any]] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        from .reporting import build_verification_report

        return build_verification_report(
            memo=memo,
            tickers=tickers,
            config=self.config,
            as_of_date=as_of_date,
            mode="agentic",
            prefetched_results=prefetched_results,
            source_results=source_results,
            progress_callback=progress_callback,
        )


def _agent_instructions(tool_profile: str) -> str:
    names = ", ".join(tool_names_for_profile(tool_profile))
    return (
        "You are a financial credibility agent. Verify claims using official evidence first. "
        "When the user input looks like copied webpage/article text, first remove advertisements, sponsor blocks, "
        "navigation, cookie prompts, duplicate lines, and unrelated boilerplate; use only the cleaned statement for "
        "entity extraction, claim decomposition, source selection, and retrieval. "
        "Use multiple tools when needed, but avoid repeating identical calls. "
        "Do not provide investment advice. Preserve uncertainty and human-review flags. "
        "A fact-checkable claim must state an objective, falsifiable property of an asset, issuer, security, or macro series. "
        "Strictly skip fact checking for forecasts, opinions, investment judgments, discussion questions, "
        "management/investor communication purpose, reassurance framing, talk/discussion framing, "
        "and vague non-falsifiable market commentary. In particular, do not retrieve evidence or verify claims "
        "such as 'priced in', 'delivered another beat', 'keeps beating quarter after quarter', or analyst color "
        "unless the claim states a concrete objective metric, period, value, and comparison baseline. "
        "Before choosing retrieval tools, combine the claim with the detected asset class: "
        "equity/ETF/index price or return moves can use historical_prices; issuer fundamentals use SEC or company fundamentals; "
        "corporate acquisition, merger, takeover, stake, or M&A claims need event evidence such as 8-K/press release/web discovery "
        "and must not use SEC Company Facts, EPS, revenue, or other XBRL numeric facts as proof of the transaction; "
        "macro, rates, FX, commodities, credit, fixed income, and derivatives use their official series/regulatory sources. "
        "Do not call a tool just because one word overlaps when the source cannot verify that property. "
        "Before retrieve_evidence or build_evidence_pack, infer the relevant time window from the full context "
        "including title, dateline, publication timestamp, weekdays, today/yesterday, fiscal periods, and prior-period wording; "
        "pass the event/release date as as_of_date so old news is not checked against the latest available data. "
        f"Available tool profile: {tool_profile}. Tools: {names}. "
        "For factual numeric claims, retrieve evidence before verification, canonicalize facts when possible, "
        "then run numeric/source/atomic verification before concluding."
    )


def _user_prompt(memo: str, tickers: list[str], as_of_date: str | None) -> str:
    return json.dumps(
        {
            "task": "verify_financial_claims",
            "memo": memo,
            "tickers": tickers,
            "as_of_date": as_of_date,
            "instruction": "Call tools as needed. Stop when enough evidence exists for a concise final assessment.",
        },
        ensure_ascii=False,
    )


def _inject_known_args(
    name: str,
    args: dict[str, Any],
        as_of_date: str | None,
        prefetched_results: list[dict[str, Any]] | None,
        source_results: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    updated = dict(args)
    if as_of_date and name in {"retrieve_evidence", "build_evidence_pack"} and not updated.get("as_of_date"):
        updated["as_of_date"] = as_of_date
    if prefetched_results is not None and name in {"retrieve_evidence", "build_evidence_pack"} and "prefetched_results" not in updated:
        updated["prefetched_results"] = prefetched_results
    if source_results is not None and name in {"retrieve_evidence", "build_evidence_pack"} and "source_results" not in updated:
        updated["source_results"] = source_results
    return updated


def _first_fact_checkable_claim_text(claims_payload: dict[str, Any]) -> str | None:
    factual_values = {argument_type.value for argument_type in FACTUAL_TYPES}
    for item in claims_payload.get("claims") or []:
        if item.get("argument_type") not in factual_values:
            continue
        text = item.get("text")
        if text:
            return str(text)
    return None


def _entity_targets(entities_payload: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for value in entities_payload.get("tickers") or []:
        if value:
            targets.append(str(value))
    for item in entities_payload.get("entities") or []:
        value = item.get("ticker") or item.get("symbol")
        if value:
            targets.append(str(value))
    for group in (entities_payload.get("asset_groups") or {}).values():
        for item in group or []:
            value = item.get("ticker") or item.get("symbol")
            if value:
                targets.append(str(value))
    seen = set()
    deduped = []
    for value in targets:
        upper = value.upper()
        if upper in seen:
            continue
        seen.add(upper)
        deduped.append(upper)
    return deduped


def _loads_args(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, dict) else {}


def _stable_args(args: dict[str, Any]) -> str:
    return json.dumps(args, sort_keys=True, ensure_ascii=True, default=str)


def _run_id(memo: str, tickers: list[str], as_of_date: str | None, tool_profile: str) -> str:
    return "agent_" + _sha256("|".join([memo, ",".join(tickers), str(as_of_date), tool_profile]))[:12]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _emit(
    callback: Callable[[dict[str, Any]], None] | None,
    step: str,
    status: str,
    summary: str,
    outputs: dict[str, Any] | None = None,
) -> None:
    if callback:
        callback({"step": step, "status": status, "summary": summary, "inputs": {}, "outputs": outputs or {}})
