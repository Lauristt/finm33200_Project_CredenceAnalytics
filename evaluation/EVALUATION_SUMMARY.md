# Evaluation: Does the Credence Analytics agent work — and does AI help?

We evaluate a financial-claim verification agent on real, labeled data. The front end
(entity extraction, classification) works reasonably. The **verdict stage is the weak point**:
even when it finds data that matches, it almost never confirms a true claim. We separate the
agent's genuine errors from one deliberate design choice — that it checks truth *as of now*.

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

**A scoping note first.** By design the agent checks whether a statement is true *right now*, so it
fetches the *latest* data. That is a reasonable choice for a "is this currently true?" checker, so we
do **not** count it as a bug. (It does limit dated/historical statements — see §6.) The genuine
problems are below.

### Cause 1 — Even when the data matches, it won't commit to "true" (systemic — the core problem)
Across 50 true statements it confirmed exactly **one**. The verdict caps at `partially_supported` and
almost never reaches `supported`. Example: NVIDIA's reported revenue matched the filing **exactly**,
yet the verdict was `partially_supported`, not `supported`. This has nothing to do with data freshness —
the number lined up and it still would not affirm. The logic is structured *not* to say "true": matching
evidence yields "partial", and only a rare configuration produces a clean "supported". The AUC of 0.34
confirms it: confidence does not separate true claims from false ones.

### Cause 2 — SEC: it compares against the wrong reporting period
A company files the *same* metric for many overlapping windows at once. Apple's revenue, for example:

| period (≈ ending 2026-03-28) | value |
|---|---|
| fiscal **Q2** (3 months) | **$111.2B** |
| first **half-year** (Q1+Q2, 6 months) | $254.9B |
| prior **quarter** (Dec) | $143.8B |
| full **fiscal year** | $416.2B |

(Note $143.8B + $111.2B ≈ $254.9B — these are the *same metric over different-length windows*, all correct.)
Fed the true claim *"Apple's Q2 revenue was $111.2 billion,"* the agent compared $111.2B against a
**different period's** figure (e.g. the half-year $254.9B), saw they differed, and judged the true claim
**`contradicted`**. **This is not a freshness issue** — Q2, the half-year and the full year all coexist as
current data; the agent has to *match the period* (read the "Q2" and pick that row), and it doesn't.

### Cause 3 — (secondary) misclassification, unmapped metrics & wrong unit
- Some real reported figures (e.g. *"Microsoft reported revenue of $82.89B"*) were classified as
  `forecast`/`opinion` and never fact-checked.
- Segment metrics (*iPhone revenue*, *AWS revenue*) aren't in the agent's mapped concepts, so there is
  nothing to compare against.
- For year-over-year claims (*"U.S. consumer prices rose 3.8%"*) the agent compares "3.8" against the CPI
  **index level** (332.4) — a **unit** mismatch it can never reconcile.

## 4. Does AI help? (per stage)
- **Entity extraction — yes** (80.5% → 89.4% with the LLM).
- **Classification — n/a** (rule-based; AI not used).
- **Verdict — AI is not the bottleneck;** the failure is a reluctant verdict rule (won't say "true") and
  period/unit matching, not the model. AI is necessary but not sufficient here.

## 5. Bottom line
The agent's front end works reasonably and AI improves extraction, but the **verdict stage almost never
confirms a true claim** (1/50; AUC 0.34) — and, crucially, **it won't do so even when the data matches
exactly** (NVIDIA). That, plus comparing a claim against the wrong SEC reporting period, is the real
weakness. The agent's "check as of now" design is itself reasonable; the gap is that even correct, current
matches don't get affirmed.

## 6. Limitations & future work
- Verdict accuracy is evaluated on US-equity/macro claims the sources actually cover; opinion/forecast have
  no ground truth (we only check classification); crypto/exotic facts are out of scope.
- **By design it verifies as-of-now.** *Usability improvement:* add **as-of-date** matching so dated/historical
  statements (e.g. *"the S&P 500 closed at 7,501.24 on May 15"*) are checked against that date rather than the
  latest value, and add **unit** matching (e.g. `units=pc1` for "rose X%").
- **Period matching (SEC):** read the claim's fiscal period (Q2 / half-year / FY) and pick the matching
  reporting window instead of an arbitrary one.
- **Let matches count:** allow a confirmed period+value match to reach `supported`, instead of capping at
  `partially_supported` — this is what would actually raise true-claim accuracy.
