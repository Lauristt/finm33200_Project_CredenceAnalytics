# Evidence Summary Skill

Use this workflow when a human needs a compact review brief.

1. Start from a report payload or `EvidencePack`.
2. Use `summarize_evidence_pack`.
3. Preserve claim ids, verdicts, confidence, human-review flags, and source URLs.
4. Do not add unsupported facts.
5. Separate verified claims from skipped opinions or forecasts.
6. Include the audit report summary when available.

The summary should be extractive. It should make review faster, not replace the underlying evidence.

