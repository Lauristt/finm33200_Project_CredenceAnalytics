# Evaluation: Does the Credence Analytics agent work — and does AI help?

We evaluate a financial-claim verification agent on real, labeled data. The front end
(entity extraction, classification) works reasonably. The **verdict stage is the weak point**:
it confirms only 1 of 50 true claims and cannot separate true from false. A fact-checker can fail
in two directions, and we measure both — **wrongly rejecting true claims** and **failing to catch
false ones** — and find they share a single root cause: comparing the claim against the wrong moment.

## 1. How we evaluated — a real-news benchmark

- **113 real statements** from Yahoo Finance across stocks, macro, commodities, FX, indices,
  rates, crypto and five claim types (numeric, factual, opinion, forecast, causal). Factual
  statements are labeled `true` and **each cross-checked against SEC/FRED**; a perturbed copy
  (changed number/date) makes a matched `false`. Opinion/forecast carry no truth value.
- **Coverage.** The set spans **7 asset classes** — equities (56), macro (18), commodities (12), indices (9),
  FX (8), rates (6), crypto (4) — drawn from **80+ distinct news items**, so the results reflect cross-asset
  behavior rather than an artifact of a single ticker or data feed.
- **113 total = 86 fact claims (50 `true` / 36 `false`) + 27 opinion/forecast/causal with no truth value.**
  Classification (§2.1) is scored on all 113; the verdict test (§2.2) is scored only on the 86 that have an
  objective true/false answer — you can't grade a verdict on an opinion or a forecast.
- **Design decision — robustness vs. retrieval.** Perturbing figures taken from the *same*
  database the agent queries would only test **retrieval** (can it fetch a row it was handed?).
  Feeding it **real, independently-sourced news** tests **real-world verification** (can it judge
  a statement as a human would encounter it?). We deliberately chose the harder, more meaningful test.

## 2. What we measured

### (1) Can it classify a claim correctly?
| Stage | Accuracy |
|---|---|
| Entity / asset-class extraction | 80.5% (rules) → **89.4%** (rules + LLM) |
| Claim-type classification | **84.5%** (rule-based) |
| Fact-check routing (opinion/forecast skipped) | **84.1%** |

### (2) For fact/numeric claims, is the verdict right?
| Metric | Real news (n = 86 fact claims) |
|---|---|
| Overall accuracy | **≈36%** (31/86) |
| True claims confirmed (`verified`/`supported`) | **1 / 50** |
| False claims caught (`contradicted`) | 30 / 36 |
| Confidence AUC (true vs false) | **0.34** |

## 3. Where the errors come from — the two directions

### 3A. Wrongly rejecting true claims (false rejection) — the big problem
Of 50 true claims, only **1** was confirmed; **18 (36%) were actively marked `contradicted`** (declared
false) and **17 (34%) stalled at `partially_supported`**. Three causes:

**(i) Time mismatch — the leading cause of the 18 wrong `contradicted` verdicts.** The agent fetches a
value for the *wrong moment* and compares against that.
> *"115,000 nonfarm payrolls were added in April 2026"* (true for April) → `contradicted`, reason
> *"the evidence shows [a different month's figure]."* Same on *"Brent crude ≈ $105 a barrel"* and
> *"copper at $6.11 per pound"* — the claim names a point in time; the agent pulls the latest value.

A specific flavor is **SEC time granularity**: the same metric is filed for many overlapping windows, and
the agent picks the wrong one —

| Apple revenue, period (≈ ending 2026-03-28) | value |
|---|---|
| fiscal **Q2** (3 months) | **$111.2B** |
| first **half-year** (Q1+Q2) | $254.9B |
| full **fiscal year** | $416.2B |

Fed *"Apple's Q2 revenue was $111.2 billion,"* the agent compared against a different period's figure and
returned `contradicted`. **Partly by design:** the agent judges truth *as of now*, so fetching the latest
value is reasonable; the gap is only for **dated/historical** claims. *Future work:* add **as-of-date** and
fiscal-period control.

**(ii) Systemic conservatism — it won't confirm even when evidence matches** (the 17 `partially_supported`).
On one true claim the agent's own log says *"All material numeric values in the claim were matched directly
in the evidence,"* yet it still returned `partially_supported`, not `verified`. Mechanism: **all-or-nothing
matching** (`verification.py`) — `verified` requires *every* material number to match. *"Nvidia reported Q1
revenue of $81.62 billion, beating estimates of $79.18 billion"*: $81.62B is in the filing, but the analyst
estimate $79.18B is in no official source, so the rule never sees "all matched."

**(iii) Misclassification** — **12 (24%)** true claims were tagged `forecast`/`opinion` and skipped (e.g.
*"Microsoft reported revenue of $82.89B"*); segment metrics (*iPhone*, *AWS*, *Greater China*) aren't mapped.

### 3B. Failing to catch false claims (false acceptance) — smaller, but revealing
The agent catches false claims fairly well — **30 of 36 (83%)** are `contradicted`. But the **6 it misses**
(5 `partially_supported`, **1 wrongly `supported`**) fail for the **same time-mismatch reason**, only in
reverse: a false number coincidentally lines up with a *different period's* real value.
> A false **Alphabet** claim was rated `supported`; the agent's reason matched it against *"the fiscal year
> ending 2023-12-31 … approximately $307.39 billion"* — the **wrong year**. And on two other false claims it
> logged *"All material numeric values … were matched directly,"* because the false figures happened to
> appear somewhere in the multi-number evidence.

**The punchline:** the *same* root cause — comparing against the wrong moment — drives errors in **both**
directions. Misaligned time turns a true claim into a `contradicted` (3A) and lets a false claim slip through
as `supported` (3B). Time alignment is the linchpin.

## 4. Does AI help? (per stage) — value-add is perception, not logic
- **Entity extraction — yes** (80.5% → 89.4%). The LLM reads *unstructured context* — which token is the
  asset, which is an action, which is a number — that regex/keyword rules can't disentangle. Real, AI-only value.
- **Classification — n/a** (rule-based; AI not used).
- **Verdict — AI is not the bottleneck.** The failure is the *verdict logic* (time alignment + all-or-nothing
  matching), not the model. AI's value-add is **limited to perception (reading the claim), not the logic.**

## 5. Bottom line
The front end works reasonably and AI improves *perception*, but the **verdict stage confirms only 1 of 50
true claims** and can't tell true from false (AUC 0.34). Both error directions trace to one root cause —
**comparing the claim against the wrong moment** — compounded by an **all-or-nothing rule that won't confirm**
unless every number matches. The "check as of now" design is reasonable; the gap is turning correct,
time-aligned evidence into a correct verdict.

> **Human vs. agent.** A human reads *"115,000 payrolls added in April"* and looks up *April*; reads *"Q1
> revenue of $81.62B, beating estimates of $79.18B"* and confirms the $81.62B while ignoring the estimate. The
> agent pulls the latest value (wrong moment) and demands *every* number match. **The gap is judgment, not data.**

## 6. Limitations & future work
- Verdict accuracy is evaluated on US-equity/macro claims the sources actually cover; opinion/forecast have
  no ground truth (we only check classification); crypto/exotic facts are out of scope.
- **As-of-date + fiscal-period control (the time-alignment fix)** — fixes *both* error directions: query the
  claim's *date* (`observation_start/end`) and unit (`units=pc1` for "rose X%"), and match the SEC period
  (Q2 / half-year / FY) instead of an arbitrary one.
- **Replace the all-or-nothing matcher with LLM reasoning,** so a claim whose official figure matches can be
  confirmed even when it also mentions a non-official number (e.g. an analyst estimate).
