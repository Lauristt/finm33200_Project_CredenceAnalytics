# Credence Analytics Demo Guide

This guide shows deterministic examples for the explainable verification,
provenance, and auditability upgrade.

## Single Equity Demo

```bash
PYTHONPATH=src python -m financial_credibility \
  "Apple revenue grew 6% year over year." \
  --ticker AAPL \
  --as-of-date 2025-11-01 \
  --prefetched-json examples/demo_equity_supported.json \
  --pretty
```

Expected features: verified equity coverage, evidence provenance, claim
explanation, source-selection explanation, and audit trace.

## Mixed Asset Report Demo

Use the Web UI or `build_verification_report()` with:

```text
Apple revenue grew 6% year over year while CPI rose and WTI rallied.
```

Expected features: AAPL is fully verified, while CPI and WTI are marked as
detected-only assets in the Verification Coverage section.

## Human Review Demo

```bash
PYTHONPATH=src python -m financial_credibility \
  "Apple revenue accelerated due to stronger demand." \
  --ticker AAPL \
  --as-of-date 2025-11-01 \
  --prefetched-json examples/demo_human_review.json \
  --pretty
```

Expected features: human-review reason explanations and provenance showing the
non-official evidence source.

## Batch Demo

```bash
PYTHONPATH=src python -m financial_credibility \
  --batch-input examples/demo_batch_input.csv \
  --batch-output batch_results.json \
  --mode strict \
  --pretty
```

Expected features: batch summary with per-row results and recoverable row-level
errors.
