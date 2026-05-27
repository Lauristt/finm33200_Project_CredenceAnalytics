# Evaluation: Does the Credence Analytics agent work — and does AI help?

We evaluate a financial-claim verification agent on real, labeled data. The front end
(entity extraction, classification) works reasonably, but the **verdict stage is unreliable**:
it almost never confirms a true claim. The dominant reason is a single, deep weakness —
**time/period alignment** — plus a structural reluctance to ever say "true".

## 1. How we evaluated — a real-news benchmark

- **113 real statements** from Yahoo Finance across stocks, macro, commodities, FX, indices,
  rates, crypto and five claim types (numeric, factual, opinion, forecast, causal). Factual
  statements are labeled `true` and **each cross-checked against SEC/FRED**; a perturbed copy
  (changed number/date) makes a matched `false`. Opinion/forecast carry no truth value.
- **Why real news, not figures from a database:** the job is to judge whether a *real-world*
  statement is accurate. Perturbing numbers taken from the same database the agent queries would
  be too easy and overstate performance — so we use real statements with verified labels.

## 2. What we measured

### (1) Can it classify a claim correctly?
| Stage | Accuracy |
|---|---|
| Entity / asset-class extraction | 80.5% (rules) → **89.4%** (rules + LLM) |
| Claim-type classification | **84.5%** (rule-based) |
| Fact-check routing (opinion/forecast skipped) | **84.1%** |

### (2) For fact/numeric claims, is the verdict right?
| Metric | Real news |
|---|---|
| Overall accuracy | **≈36%** |
| True claims confirmed (`supported`) | **1 / 50** |
| False claims caught (`contradicted`) | ≈30 / 36 |
| Confidence AUC (true vs false) | **0.34** |

Headline: the agent **almost never confirms a true claim** (1/50) and can't separate true from
false (AUC ≈ 0.34) — fine at flagging false claims, but effectively useless at confirming a true one.

## 3. Where the errors come from

### Cause 1 — Time / period mismatch (the core weakness)
The agent usually finds the right metric, but **lines it up against the wrong point in time** —
so a true claim's number "doesn't match" and gets rejected. It shows up in two ways:

**(a) SEC: overlapping reporting periods.** A company files the *same* metric for many overlapping
windows. Apple's revenue, for example, appears as:

| period (ending 2026-03-28 era) | value |
|---|---|
| fiscal **Q2** (3 months) | **$111.2B** |
| first **half-year** (6 months) | $254.9B |
| prior **quarter** (Dec) | $143.8B |
| full **fiscal year** | $416.2B |

Fed the true claim *"Apple's Q2 revenue was $111.2 billion,"* the agent compared $111.2B against a
**different period's** figure (e.g. the half-year $254.9B or the annual $416.2B), saw they differed,
and judged the true claim **`contradicted`**. The number was right; it was matched to the wrong period.

**(b) FRED: the fetch is date- and unit-blind.** For macro/market series the agent always pulls the
*latest* observation and the *raw level* — never the claim's date or unit:
- *"The S&P 500 closed at 7,501.24 on May 15, 2026."* (true for May 15) → the agent fetched FRED's
  **latest** value (7,473.47 on **May 22**) and compared against that, never looking up May 15 → mismatch.
- *"U.S. consumer prices rose 3.8% over 12 months."* (a year-over-year **percent**) → the agent fetched
  the CPI **index level** (332.4) and compared "3.8" against "332.4" → a **unit** mismatch it can never reconcile.

→ Whether the source is SEC or FRED, the same failure recurs: **the value is found, but aligned to the
wrong period or unit, so a true claim is rejected.** This is the single biggest weakness.

### Cause 2 — Found the data but won't commit to "true" (systemic)
Even when the figure *does* line up, the verdict tops out at `partially_supported` and almost never
reaches `supported`. Across 50 true statements it confirmed exactly **one**. Example: NVIDIA's reported
revenue matched the filing exactly, yet the verdict was `partially_supported`, not `supported`. The logic
is structured *not* to affirm — matching evidence yields "partial", and only a rare configuration produces
a clean "supported". So it is structurally reluctant to ever call a true claim true.

### Cause 3 — (secondary) misclassification & unmapped metrics
A few failures are upstream: some real reported figures (e.g. *"Microsoft reported revenue of $82.89B"*)
were classified as `forecast`/`opinion` and never fact-checked; and segment metrics (*iPhone revenue*,
*AWS revenue*) aren't in the agent's mapped concepts, so there is nothing to compare against.

## 4. Does AI help? (per stage)
- **Entity extraction — yes** (80.5% → 89.4% with the LLM).
- **Classification — n/a** (rule-based; AI not used).
- **Verdict — AI is not the bottleneck;** the failure is time/period alignment and a reluctant verdict
  rule, not the model. AI is necessary but not sufficient here.

## 5. Bottom line
The agent's front end works reasonably and AI improves extraction, but its **verdict stage almost never
confirms a true claim** (1/50; AUC 0.34). The dominant cause is **time/period mismatch** — it finds the
right number but aligns it to the wrong reporting period (SEC) or only the latest/raw value (FRED) — and
even when the number matches, the logic refuses to escalate past `partially_supported`. *The core problem
is temporal alignment of evidence, not the AI model.*

## 6. Limitations & future work
- Verdict accuracy is evaluated on US-equity/macro claims the sources actually cover; opinion/forecast have
  no ground truth (we only check classification); crypto/exotic facts are out of scope.
- **Future work (the fix that matters):** make verification **period- and unit-aware** — for SEC, match the
  claim's fiscal period to the right reporting window; for FRED, query the claim's *date*
  (`observation_start/end`) and the right unit (e.g. `units=pc1` for "rose X%"). Then let a confirmed
  period+value match reach `supported`, instead of capping at `partially_supported`.
