# Audit Chain Review Skill

Use this workflow when reviewing an existing report, `EvidencePack`, `AuditTrace`, or `AgentTrace`.

1. Read the final report payload.
2. Read the run-level `audit_trace`.
3. Read the model-level `agent_trace`.
4. Run deterministic checks first:
   - evidence references exist
   - canonical facts exist
   - calculations recompute
   - tool order is sensible
   - official-first policy is respected
   - low-confidence claims trigger human review
5. Use narrow reasoning review only for evidence-to-conclusion logic.
6. Summarize findings by severity and category.
7. Convert recurring findings into tests or tool-description edits.

Good audit findings include:

- affected claim or tool
- supporting trace references
- severity
- recommended fix

