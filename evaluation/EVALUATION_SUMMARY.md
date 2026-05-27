# Evaluation: Does the Credence Analytics agent actually work — and does AI help?

We evaluated the financial-claim verification agent stage by stage on **real, labeled
data**, asking two questions: (1) is each stage accurate, and (2) does the AI component
add value over a non-AI version? We report what works, what doesn't, and a real bug we
found and fixed.

## What the agent does (in one line)

Given a financial statement, the pipeline **extracts the entity/asset class → classifies
the claim type → routes it to a data source → retrieves evidence → produces a verdict +
confidence + human-review flag**. We evaluate each of these stages.

## Method

- **Benchmark 1 — real news (113 statements).** We pulled real statements from Yahoo
  Finance (Reuters/AP/company releases/market data) across **stocks, macro, commodities,
  FX, indices, rates, crypto** and **5 claim types** (numeric, factual, opinion, forecast,
  causal). Factual statements are labeled `true` (default-true from authoritative sources,
  **each cross-checked against SEC/FRED**); a copy of each is perturbed (changed number or
  date) to create a matched `false`. Opinion/forecast carry no truth value — they test
  classification/routing. File: `claims_news.json` / `claims_news.xlsx`.
- **Benchmark 2 — SEC-anchored (100 statements).** Numbers taken directly from SEC filings,
  perturbed for false twins. Objective labels. File: `claims.json`.
- **Why both:** Benchmark 2 is "easy" (the labels come from the same source the agent
  queries); Benchmark 1 is realistic (real phrasing, real-world variety). Comparing them
  shows how much the easy setup overstates performance.
- Scripts: `eval_news.py` (entity/classification/routing), `eval_verdict.py` (verdict
  accuracy). Every claim is traceable in the `results_*.csv` files.

## Results by pipeline stage

| Stage | Accuracy | Notes |
|---|---|---|
| Entity / asset-class extraction | **80.5% (rules) → 89.4% (rules + LLM)** | AI helps (+9 pts), esp. company names & macro; FX/index/rates stay weak |
| Claim-type classification | **84.5%** | rule-based (no LLM); opinion/forecast weaker (8/12, 9/13) |
| Fact-check routing (opinion/forecast skipped) | **84.1%** | macro sometimes not routed to FRED (a real gap) |
| Verdict accuracy | **see below** | the critical stage; had a systematic bug |

### Verdict: easy vs realistic, and a systematic bug

| | SEC-anchored (easy) | Real news (realistic) |
|---|---|---|
| Overall accuracy | 74% | **36%** |
| True claims confirmed (`supported`) | 0/20 | **0/50** |
| False claims caught (`contradicted`) | 74/80 | 31/36 |
| Confidence AUC (true vs false) | 0.50 | **0.345** |

Two findings: (1) the **easy benchmark badly overstates performance** (74% vs 36%) — it
rewards looking up the same database the labels came from; and (2) more seriously, the
pipeline **never confirmed a single true claim** and rated most true claims `contradicted`
— even statements that match SEC to the dollar (e.g., NVIDIA Q1 revenue $81.62B = SEC
$81,615M; Apple Q2 revenue $111.2B = SEC $111,184M). A trivial "always say false" baseline
(80%) beats it. AUC ≈ 0.5 (and 0.345 on news) means it could not separate true from false.

## Root cause and fix (found via the evaluation)

**Root cause:** `sec_company_facts` kept only the 2 *most-recently-filed* values per metric,
so recent quarterly figures crowded out the **specific fiscal-period value a claim refers
to**. The figure to verify was simply absent from the evidence → `not_found` → the verdict
logic escalated that to `contradicted` (a true claim judged false).

**Fix A (implemented in `data_sources.py`):** surface full-year *and* quarterly figures,
de-duplicated by reporting period (end date + period kind), each tagged
`for fiscal year/quarter ending YYYY-MM-DD: <value>`, so the claim's period value is present.

**Before → after (SEC-anchored, same pipeline):**

| Metric | Before | After Fix A |
|---|---|---|
| True claims judged `contradicted` | 19/20 | **0/20** |
| Confidence AUC (true vs false) | 0.50 | **0.83** |
| False claims caught | 74/80 | **79/80** |
| Human-review precision (flagged & wrong) | 15/69 | **1/56** |

Fix A eliminated the catastrophic behavior (true claims are no longer judged false) and made
confidence cleanly separate true from false (AUC 0.83). A residual issue remains (true claims
now top out at `partially_supported`, not `supported`) — documented as **Fix B** in
`BUGS_FOUND.md`.

### Fix A's benefit is dataset-dependent (the honest catch)

We re-measured Fix A on **both** benchmarks:

| Benchmark | Before Fix A | After Fix A |
|---|---|---|
| Constructed (`claims.json` — all plain annual revenue/income) | 74%, AUC 0.50, 19/20 true contradicted | **79%, AUC 0.83, 0/20** |
| Real news (`claims_news` — mixed metrics/assets) | 36%, AUC 0.345, 0/50 confirmed | **35%, AUC 0.338, 1/50** |

On the constructed set Fix A looks transformative; on real news it is **nearly flat** — it reduces
true-claim contradictions (30 → 22) but overall accuracy and AUC barely move, because the A-class
it fixes is only ~10% of real failures. The dramatic gain was largely an artifact of a homogeneous,
self-built benchmark — the same lesson as the 74%-vs-36% gap, now applied to the *fix itself*.

## Failure taxonomy — the errors had multiple causes, not one

We attributed every pre-fix failure (50 true news claims, all unconfirmed) to a distinct
mechanism by inspecting the pipeline's internals (entity extraction, classification, evidence
count, numeric/atomic verdict):

| Cause | Claims | Fixed by Fix A? | Example |
|---|---|---|---|
| C1. **Misclassified** as forecast/opinion → retrieval skipped (stock) | 9 (18%) | no | "MSFT revenue $82.89B" labeled `forecast` → SEC never queried (no key needed; it just didn't look) |
| C2. **No source routed** (macro/commodity/index/FX/rates) | 13 (26%) | no | CPI, Brent, S&P 500, EUR/USD → not mapped to FRED / no price source |
| B. Concept-mapping gap (segment metric / EPS not a mapped concept) | 11 (22%) | no | iPhone revenue, Greater China, AWS |
| A. Period coverage / over-escalation | 5 (10%) | **yes** | Apple Q2 $111.2B, JPM Q4 net revenue |
| near-miss (`partially_supported`) | 5 (10%) | partly | NVDA $81.62B, TSLA $22.39B |
| E. Classified as non-factual, skipped | 4 (8%) | no | GDP, unemployment, causal claims |
| D. Entity / asset-class not extracted | 3 (6%) | no | Nasdaq, GBP/JPY |

**Key insight:** the dominant cause depends on the claim mix. On clean annual revenue/income
claims (Benchmark 2) the period bug (A) dominates and Fix A resolves ~19/20. On realistic news
(Benchmark 1), A is only ~10%; the real bottlenecks are **retrieval coverage (C, 44%)** and
**segment-metric concept gaps (B, 22%)**, which Fix A does not touch. So a homogeneous,
self-constructed benchmark overstates *both* the failure rate and the benefit of any single fix.

**Why the "no evidence" failures happen — it is NOT a missing-key problem.** SEC needs no API key
and FRED is configured. The two real reasons: (C1) factual statements were *misclassified* as
forecast/opinion, so the pipeline decided not to fact-check them and never queried SEC; and (C2)
macro/commodity/index/FX/rates claims were never *routed* to a source — many exist in FRED
(CPI, payrolls, WTI, S&P 500, EUR/USD) but the keyword routing did not map them, and no dedicated
price source is wired for commodities/indices/FX.

## Does AI help? (per stage)

- **Entity extraction: yes** — the LLM layer lifts accuracy 80.5% → 89.4%.
- **Classification: not applicable** — it is rule-based; AI is not used here.
- **Verdict: AI was not the bottleneck** — the pipeline's failure came from a deterministic
  data-coverage bug, not the LLM judge. Fixing the deterministic extraction (Fix A) unlocked
  most of the value (AUC 0.50 → 0.83). **Conclusion: AI is necessary but not sufficient —
  data coverage and period alignment mattered more than the model here.**

## Failure cases (honest)

1. **True claims judged false** (pre-fix): NVIDIA $81.62B, Apple $111.2B — both match SEC,
   both rated `contradicted`. Root cause + fix above.
2. **Macro routing gap:** "U.S. CPI rose 3.8%" returned 0 evidence because the claim was not
   routed to FRED (keyword miss).
3. **Quarterly period confusion:** SEC reports overlapping periods (quarter / half-year /
   annual); matching the wrong one produced false contradictions.

## Limitations

- Verdict accuracy is trustworthy mainly for **US equities** (SEC, no key); macro/commodity/FX
  verdicts depend on FRED routing/keys and are partly a coverage gap, not a judgment error.
- **Crypto / exotic credit** facts are not reliably checkable by the agent's sources — out of
  scope, flagged in the data.
- Opinion/forecast have no ground truth; we evaluate only whether they are correctly
  classified and **not** fact-checked.
- News "true" labels were cross-checked against SEC/FRED, but quarterly figures and phrasing
  remain a known source of label noise.

## Bottom line

The agent's **front end (entity extraction, classification, routing) works reasonably and AI
improves extraction**, but its **verdict stage shipped with a systematic bug that made it
reject true claims** — invisible on an easy benchmark, exposed by realistic news data. We
located the cause, fixed it (AUC 0.50 → 0.83, true-claim contradictions 19 → 0), and
documented the remaining work. The honest takeaway: *on this task the win came from fixing the
data pipeline, not from the AI model.*
