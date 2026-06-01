# Claude Project Setup For Credence Analytics

Keep this file separate from runtime code. It is a team workflow guide for Claude/Codex-style project organization.

## Recommended Project Instructions

Use these instructions in a Claude Project or comparable AI workspace:

```text
You are helping maintain Credence Analytics, a local financial credibility toolkit.
Prefer official and auditable evidence. Do not provide investment advice.
When verifying claims, preserve uncertainty, human-review flags, source provenance, and replayable traces.
Use the repo's tool registry, profiles, and audit workflow instead of inventing new ad hoc tools.
For code changes, keep APIs backward compatible unless the task explicitly asks for a breaking change.
```

## Required Context Files

Pin or attach:

- `README.md`
- `docs/AGENTIC_ARCHITECTURE.md`
- `src/financial_credibility/tool_registry.py`
- `src/financial_credibility/tool_profiles.py`
- `src/financial_credibility/multi_tool_agent.py`
- `src/financial_credibility/audit_agent.py`
- `src/financial_credibility/reporting.py`
- `src/financial_credibility/tool_runtime.py`
- `evaluation/EVALUATION_SUMMARY.md` when working on quality evaluation.

## Workflow Recipes

Study project:

- Ask the model to explain one module at a time.
- Use `summarize_evidence_pack` on sample reports.
- Ask for quizzes around source routing, canonical facts, and audit findings.

Research project:

- Keep a corpus of sample memos and expected verdicts.
- Run `multi_tool` with `agent_trace_out`.
- Run `audit_verification_chain` on traces and collect recurring failure modes.
- Convert recurring findings into test cases.

Career or portfolio project:

- Keep demos deterministic with `prefetched_results`.
- Show both the final report and the audit report.
- Emphasize official-first verification, traceability, and human-review escalation.

## Review Cadence

Weekly:

- Run the full pytest suite.
- Run a small prefetched AAPL/NVDA demo.
- Review `review_tool_surface(profile="agent_core")`.
- Sample one successful trace and one failed trace with `audit_verification_chain`.

Before demos:

- Use no-key prefetched examples unless live data access is part of the demo.
- Confirm `SEC_USER_AGENT` is set if live SEC calls are enabled.
- Confirm the report includes a no-investment-advice statement or equivalent project-level framing.

