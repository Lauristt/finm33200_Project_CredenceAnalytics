# Evaluation: Does the Credence Analytics agent work — and does AI help?

We evaluate a financial-claim verification agent on real, labeled data, and report
honestly where it works and where it fails. There is **no single root cause** for its
errors — the failures come from several distinct mechanisms, dominated by *data coverage*,
not by any one bug.

## 1. How we evaluated — a real-news benchmark

- **113 real statements** from Yahoo Finance across stocks, macro, commodities, FX, indices,
  rates, crypto and five claim types (numeric, factual, opinion, forecast, causal). Factual
  statements are labeled `true` and **each cross-checked against SEC/FRED**; a copy is perturbed
  (changed number/date) to make a matched `false`. Opinion/forecast carry no truth value (they
  test classification only). Every claim is traceable in the `results_*.csv` files.
- **Why real news, not figures pulled from a database:** the project's job is to judge whether a
  *real-world* statement is accurate. A benchmark built by perturbing numbers taken from the same
  database the agent queries would be too easy and would overstate performance — so we evaluate on
  real statements, with labels verified against the primary sources.

## 2. What we measured

### (1) Can it classify a claim correctly?
Does it sort each statement into the right type (numeric / factual / opinion / forecast /
causal) and correctly route opinion/forecast to "not fact-checked"?

| | Accuracy |
|---|---|
| Entity / asset-class extraction | 80.5% (rules) → **89.4% (rules + LLM)** |
| Claim-type classification | **84.5%** (rule-based; no LLM) |
| Fact-check routing (opinion/forecast skipped) | **84.1%** |

### (2) For fact/numeric claims, is the true/false verdict right?

| Metric | Real news |
|---|---|
| Overall accuracy | **≈35%** |
| True claims confirmed (`supported`) | **1 / 50** |
| False claims caught (`contradicted`) | ≈30 / 36 |
| Confidence AUC (true vs false) | **0.34** |

Headline: the agent **almost never confirms a true claim** (1/50) and can't separate true from
false (AUC ≈ 0.34). It is decent at *not* affirming (it flags most false claims) but effectively
useless at *confirming* a true one.

## 3. Where the errors come from (multiple causes, no single root cause)

We attributed all 50 true-claim failures on real news to a mechanism:

### a. It couldn't get the data — **44%** (the biggest cause)
- **Which data:** macro (CPI, payrolls), commodities (Brent, copper), indices (S&P 500,
  Dow), FX (EUR/USD), plus some misrouted stock claims.
- **Why — and it is NOT a missing API key** (SEC needs none; FRED is configured):
  1. **The source isn't implemented.** The system *declares* 25 data sources (BLS, BEA, ECB,
     CFTC, IMF, World Bank, …) but only ~12 have real fetchers — the rest are menu "cards"
     with no code. So non-equity assets have almost no working source except FRED.
  2. **Routing is too narrow.** FRED actually *has* CPI, payrolls, WTI, S&P 500, EUR/USD, but
     the keyword map only knows "cpi"/"inflation"/"gdp" — it never matches "consumer prices",
     "payrolls", or "Brent", so it never queries.
  - So in almost every case the data *exists in a covered source* but is **not wired/routed**;
    it is rarely that the data genuinely doesn't exist (only crypto truly lacks a source).

### b. It matched the wrong time period — **10%** (a bug we found and fixed: "Fix A")
SEC reports overlapping periods (quarter / half-year / annual). The check compared the claim's
figure to the **wrong period** → contradicted a true claim. **Fix A** (surface values tagged by
reporting period) resolved this class — but it is only ~10% of real failures, so real-news
accuracy stayed ≈35%, confirming the bottleneck is elsewhere (data coverage), not this bug.

### c. It found the data but wouldn't commit to "true" — systemic
Even when the figure matches, the verdict caps at `partially_supported` and almost never reaches
`supported` (true confirmed 1/50). The verdict logic is too conservative — it stops short of
confirming true claims.

### d. It misclassified or couldn't map the metric
- **Misclassification:** factual statements labeled `forecast`/`opinion` → never fact-checked
  (e.g., "Microsoft reported revenue of $82.89B" treated as a forecast). 9 stock claims.
- **Concept-mapping gap:** segment metrics (iPhone revenue, AWS, Greater China) aren't mapped
  SEC concepts → not retrievable even with evidence present. 11 claims.
- **Entity not extracted:** Nasdaq, GBP/JPY not recognized → nothing to query. 3 claims.

## 4. Does AI help? (per stage)
- **Entity extraction: yes** — the LLM layer lifts 80.5% → 89.4%.
- **Classification: n/a** — rule-based; AI not used.
- **Verdict: AI was not the bottleneck** — the failures are data-coverage and routing, not the
  model. AI is necessary but not sufficient here.

## 5. Limitations
- Verdict accuracy is trustworthy mainly for US equities (SEC). Macro/commodity/FX coverage is
  limited by unimplemented sources + narrow routing, not by keys.
- The system advertises broad multi-asset coverage (25 declared sources) but only ~12 are
  actually implemented — much of the "coverage" is a menu without a backend.
- Opinion/forecast have no ground truth; we only check that they are classified and *not*
  fact-checked. Crypto/exotic facts are out of scope.

## 6. Bottom line
The agent's **front end (entity extraction, classification, routing) works reasonably, and AI
improves extraction**. The **verdict stage is unreliable on realistic claims** — but there is
**no single root cause**: ~44% of failures are "couldn't get the data" (sources not implemented
or not routed — not a key problem), ~22% are concept gaps, only ~10% are the period bug we fixed,
and a systemic conservatism keeps it from confirming true claims. *The reliability bottleneck is
data coverage, not one bug.*
