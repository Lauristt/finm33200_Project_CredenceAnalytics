# Credence Multi-Tool Agent Architecture

Credence has two execution styles:

- `strict` / `agentic`: deterministic toolkit orchestration for one ticker or a memo-level report.
- `multi_tool`: a model-directed loop that can call registered tools multiple times inside a narrow profile.

The multi-tool path is additive. Existing toolkit APIs still return the same `EvidencePack` and report payload fields.

## Flow

1. `MultiToolAgentRunner.run(...)` selects a provider from `ToolkitConfig`.
2. It loads a tool profile from `tool_profiles.py`.
3. OpenAI uses Responses API function tools; Anthropic uses Messages tool-use.
4. The model may call zero, one, or many tools until it reaches a final answer, `max_steps`, repeated-call limit, or tool error.
5. Each call is executed through `execute_tool()` so the registry and runtime stay provider-neutral.
6. Every call is captured in `AgentTrace`.
7. The runner builds the normal verification report and attaches `agent_trace`.
8. If enabled, `audit_verification_chain` produces an `AuditReport`.

When no LLM provider is configured, the runner falls back to a deterministic core sequence:

`extract_entities -> map_asset_sources -> decompose_claims -> select_sources -> retrieve_evidence -> get_canonical_facts -> verify_atomic_claim -> build_audit_trace`

## Tool Profiles

Profiles keep the model from seeing an oversized tool surface.

- `one_shot`: only `build_evidence_pack`.
- `agent_core`: entity extraction, asset/source mapping, decomposition, source selection, retrieval, canonicalization, verification, aggregation, and trace construction.
- `retrieval_deep`: `agent_core` plus SEC, filings, historical prices, benchmark comparison, and vendor fundamentals.
- `audit`: audit verifier tools only.
- `review`: summary and tool-surface review tools.

Default runtime profile: `agent_core`.

Use `retrieval_deep` only when the claim needs source-specific tools, price windows, benchmark comparison, or company fundamentals. Use `one_shot` when the caller needs a stable packaged result more than intermediate control.

## Trace Schema

`AgentTrace` records model/tool behavior:

- `run_id`, `created_at`, `provider`, `model`
- `tool_profile`
- `instructions_hash`
- `tool_calls`
- `termination_reason`
- `notes`

Each `AgentToolCall` records:

- `call_id`
- `turn_index`
- `tool_name`
- `arguments`
- `status`
- `error`
- `duration_ms`
- `output_preview`
- `output_hash`

`AuditTrace` remains the verification replay trace inside each `EvidencePack`. It captures evidence, canonical facts, and verifier events. `AgentTrace` answers "what did the agent do"; `AuditTrace` answers "how was the verdict produced."

## Audit Verifier Categories

`audit_verification_chain` emits `AuditFinding` rows with severity:

- `info`
- `minor`
- `major`
- `critical`

Categories:

- `evidence`: cited facts, evidence URLs, canonical fact ids, provenance.
- `computation`: growth, ratios, spread-like and cash-flow formulas that can be recomputed.
- `tool_use`: missing steps, wrong order, repeated calls, failed calls, skipped retrieval.
- `constraint`: official-first policy, human-review flags, no-investment-advice guardrails.
- `reasoning`: whether evidence supports the conclusion; uses deterministic checks first and an optional narrow LLM judge when configured.
- `outcome`: low-weight retrospective annotation.
- `prompt`: missing model or instruction metadata.
- `tool_surface`: profile too broad or all-tools exposure.

Outcome review never overrides evidence-based verdicts.

## Entry Points

Python:

```python
from financial_credibility import MultiToolAgentRunner, ToolkitConfig

payload = MultiToolAgentRunner(ToolkitConfig.from_env()).run(
    memo="Apple revenue grew 6% year over year.",
    tickers=["AAPL"],
    as_of_date="2025-11-01",
    tool_profile="agent_core",
    max_steps=12,
    audit=True,
)
```

CLI:

```bash
PYTHONPATH=src python3 -m financial_credibility \
  "Apple revenue grew 6% year over year." \
  --ticker AAPL \
  --mode multi-tool \
  --tool-profile agent_core \
  --agent-max-steps 12 \
  --agent-trace-out agent_trace.json \
  --pretty
```

Web API:

```json
{
  "statement": "Apple revenue grew 6% year over year.",
  "tickers": ["AAPL"],
  "mode": "multi_tool",
  "tool_profile": "agent_core",
  "agent_max_steps": 12,
  "audit": true
}
```

`/api/report/stream` emits trace events for tool calls and audit findings before the final report event.

## Tool Description Policy

Every registered tool should describe:

- purpose
- use_when
- do_not_use_when
- required_prior_state
- output_means
- recommended_next_tools
- key_or_cost_notes
- common_failure_modes

Run `review_tool_surface` after adding or changing tools.
