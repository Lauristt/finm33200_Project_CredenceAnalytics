# Evaluation: Does the Credence Analytics agent work — and does AI help?

We evaluate a financial-claim verification agent on real, labeled data, and report
honestly where it works and where it fails. We also fixed two real bugs — and found that
**neither moved real-world accuracy**, because the failures are a *stack* of issues, not
one root cause.

## 1. How we evaluated — a real-news benchmark

- **113 real statements** from Yahoo Finance across stocks, macro, commodities, FX, indices,
  rates, crypto and five claim types (numeric, factual, opinion, forecast, causal). Factual
  statements are labeled `true` and **each cross-checked against SEC/FRED**; a perturbed copy
  (changed number/date) makes a matched `false`. Opinion/forecast carry no truth value (they
  test classification only). Every claim is traceable in the `results_*.csv` files.
- **Why real news, not figures from a database:** the project's job is to judge whether a
  *real-world* statement is accurate. Perturbing numbers taken from the same database the agent
  queries would be too easy and overstate performance — so we use real statements with labels
  verified against the primary sources.

## 2. What we measured

### (1) Can it classify a claim correctly?
| Stage | Accuracy |
|---|---|
| Entity / asset-class extraction | 80.5% (rules) → **89.4%** (rules + LLM) |
| Claim-type classification | **84.5%** (rule-based; no LLM) |
| Fact-check routing (opinion/forecast skipped) | **84.1%** |

### (2) For fact/numeric claims, is the true/false verdict right?
| Metric | Real news |
|---|---|
| Overall accuracy | **≈36%** |
| True claims confirmed (`supported`) | **1 / 50** |
| False claims caught (`contradicted`) | ≈30 / 36 |
| Confidence AUC (true vs false) | **0.34** |

Headline: the agent **almost never confirms a true claim** (1/50) and can't separate true from
false (AUC ≈ 0.34) — decent at flagging false claims, but effectively useless at confirming a
true one.

## 3. Where the errors come from (multiple causes, no single root cause)

We attributed all 50 true-claim failures to a mechanism:

### a. It couldn't get the data — **44%** — it never queried a source it already has
The data was reachable; the agent just didn't fetch it. **Not a missing key, not a missing source:**
  1. **Routing too narrow (≈13: macro/commodity/index/FX).** Never sent to FRED — though FRED is
     implemented and *has* CPI, payrolls, WTI, S&P 500, EUR/USD (verified). The keyword map only knew
     "cpi"/"inflation"/"gdp", so "consumer prices", "Brent", "S&P 500" never matched.
  2. **Misclassified → retrieval skipped (≈9: stock).** Labeled `forecast`/`opinion`, so the agent
     decided "not a fact" and never queried SEC (implemented, and it has the data).

### b. It matched the wrong time period — **10%** (a bug we found and fixed: "Fix A")
SEC reports overlapping periods (quarter / half-year / annual); the check compared the claim's figure
to the **wrong period** → contradicted a true claim.

### c. It found the data but wouldn't commit to "true" — systemic
Even when the figure matches, the verdict caps at `partially_supported` and almost never reaches
`supported` (true confirmed 1/50). The verdict logic is too conservative.

### d. Misclassified or couldn't map the metric
Factual statements labeled `forecast`/`opinion` → never fact-checked (9); segment metrics (iPhone
revenue, AWS) aren't mapped SEC concepts → not retrievable (11); some entities (Nasdaq, GBP/JPY) not
extracted (3).

## 4. Improvements we made (routing + Fix A) — and the result

**Fix A — period-aware SEC facts.** `sec_company_facts` kept only the 2 most-recently-filed values per
metric, so a claim's specific fiscal-period value was often absent → `not_found` → escalated to
`contradicted`. Fix: surface full-year *and* quarterly figures de-duplicated by period (tagged
"for fiscal year/quarter ending YYYY-MM-DD"), so the claim's period value is present.

**Routing fix — send macro/commodity/index/FX to FRED.** Both routing layers were too narrow: source
selection (`routing.py`) and the FRED keyword map (`data_sources.py`) only knew a few terms. Fix: expand
both with EN/ZH synonyms and aliases ("consumer prices", "Brent", "S&P 500", "EUR/USD", …) so these
claims route to FRED, which already has the series.

**Result on real news:**

| Stage | Accuracy | True confirmed | AUC |
|---|---|---|---|
| Baseline | 36% | 0 / 50 | 0.345 |
| + Fix A | 35% | 1 / 50 | 0.338 |
| + Routing fix | 36% | 1 / 50 | 0.343 |

**Neither fix moved real-world accuracy.** Each repaired a real layer — Fix A removed period-mismatch
false-contradictions, and the routing fix now *retrieves* the previously-missing macro/commodity/index/FX
data — but the verdict stayed ≈36% because the **next layer immediately blocks it:**

- **FRED fetch is date/period-blind (the root of "retrieved but matched the wrong value").** `fred()`
  always returns the *latest* raw observation, never the claim's date and never a derived value. So
  "S&P 500 closed at 7,501 on May 15" is checked against FRED's *latest* (7,473 on May 22), and "CPI rose
  3.8%" is checked against the index *level* (332), not the year-over-year %. → mismatch → still wrong.
- **CPI / payrolls are still misclassified** → skipped before retrieval.

**Takeaway:** the failures are a *stack* — routing → date/period-blind fetch → classification →
conservative verdict. Fixing one layer just exposes the next. This is the strongest evidence that there
is **no single root cause**; the bottleneck is the depth of the data/verdict pipeline, not one bug.

## 5. Does AI help? (per stage)
- **Entity extraction — yes** (80.5% → 89.4% with the LLM).
- **Classification — n/a** (rule-based; AI not used).
- **Verdict — AI was not the bottleneck;** the failures are routing, fetch-alignment, and classification,
  not the model. AI is necessary but not sufficient here.

## 6. Bottom line
The front end (entity extraction, classification, routing) works reasonably and AI improves extraction.
The verdict stage is unreliable on realistic claims, and there is **no single root cause**: ~44% of
failures are "never queried a source it already has" (routing + classification), ~22% concept gaps, only
~10% the period bug we fixed, plus a systemic conservatism. We fixed two real layers (Fix A + routing) and
**real-world accuracy did not move (≈36%)** — because each fix exposes the next problem. *The reliability
bottleneck is the depth of the data/verdict pipeline, not one bug.*

## 7. Limitations & future work
- On this benchmark, the verdict failures are routing / fetch-alignment / classification problems
  (the data is reachable), not missing data or keys.
- Opinion/forecast have no ground truth (we only check classification + routing); crypto/exotic facts
  are out of scope.
- **Future work (in priority order):**
  1. **Make `fred()` date/period-aware** — parse the claim's date and use `observation_start/end`; for
     "rose X%" claims use `units=pc1` (year-over-year). This is the root fix for "retrieved but wrong value".
  2. **Fix the factual-vs-forecast classifier** so reported figures aren't skipped before retrieval.
  3. (Lower priority, broader coverage) implement the declared-but-unimplemented sources (BLS/BEA/ECB/…).
