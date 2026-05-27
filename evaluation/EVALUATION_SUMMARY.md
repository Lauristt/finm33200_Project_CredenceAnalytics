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
| Metric | Real news |
|---|---|
| Overall accuracy | **≈36%** |
| True claims confirmed (`verified`/`supported`) | **1 / 50** |
| False claims caught (`contradicted`) | ≈30 / 36 |
| Confidence AUC (true vs false) | **0.34** |

Headline: the agent **almost never confirms a true claim** (1/50) and can't separate true from
false (AUC ≈ 0.34) — fine at flagging false claims, but effectively useless at confirming a true one.

## 3. Where the errors come from

**A scoping note first.** By design the agent checks whether a statement is true *right now*, so it
fetches the *latest* data. That is a reasonable choice for a "is this currently true?" checker, so we
do **not** count it as a bug. (It does limit dated/historical statements — see §6.) The genuine
problems are below.

### Cause 1 — Systemic conservatism: it confirms only if *every* number matches (the core problem)
This is a **design-level logic gap, not an AI failure.** In code (`verification.py`), a claim is marked
`verified` **only when every material number in the sentence is independently found in the evidence**
(`len(matches) == len(claim_numbers)`); otherwise it is downgraded to `partially_verified`. Real news
sentences bundle several numbers, but official sources can confirm only the headline fact — so true
claims almost always fall short of "all matched."

> **Example.** *"Nvidia reported first-quarter revenue of $81.62 billion, beating analyst estimates of
> $79.18 billion."* The SEC filing confirms **$81.62B exactly** — but the **analyst estimate $79.18B**
> isn't in any official source, by definition. Because the rule requires *both* numbers to match, this
> true claim is downgraded to `partially_verified`, never `verified`.

The effect is a **false-negative bias**: to avoid affirming something unproven, the logic under-confirms,
so across 50 true statements it fully confirmed exactly **one**. The AUC of 0.34 reflects the same thing —
confidence does not separate true claims from false ones. *Note this is not "too high a confidence
threshold" — there is no such gate; it is the all-or-nothing matching rule.*

### Cause 2 — Temporal granularity mismatch (SEC): it compares against the wrong reporting period
A company files the *same* metric for many overlapping windows at once. Apple's revenue, for example:

| period (≈ ending 2026-03-28) | value |
|---|---|
| fiscal **Q2** (3 months) | **$111.2B** |
| first **half-year** (Q1+Q2, 6 months) | $254.9B |
| prior **quarter** (Dec) | $143.8B |
| full **fiscal year** | $416.2B |

(Note $143.8B + $111.2B ≈ $254.9B — the *same metric over different-length windows*, all correct.)
Fed the true claim *"Apple's Q2 revenue was $111.2 billion,"* the agent compared $111.2B against a
**different period's** figure (e.g. the half-year $254.9B), saw they differed, and judged the true claim
**`contradicted`**. **This is not a freshness issue** — Q2, the half-year and the full year all coexist as
current data; the agent has to *match the granularity* (read the "Q2" and pick that row), and it doesn't.

### Cause 3 — (secondary) misclassification, unmapped metrics & wrong unit
- Some real reported figures (e.g. *"Microsoft reported revenue of $82.89B"*) were classified as
  `forecast`/`opinion` and never fact-checked.
- Segment metrics (*iPhone revenue*, *AWS revenue*) aren't in the agent's mapped concepts, so there is
  nothing to compare against.
- For year-over-year claims (*"U.S. consumer prices rose 3.8%"*) the agent compares "3.8" against the CPI
  **index level** (332.4) — a **unit** mismatch it can never reconcile.

## 4. Does AI help? (per stage) — value-add is perception, not logic
- **Entity extraction — yes** (80.5% → 89.4%). The LLM reads *unstructured context* — which token is the
  asset, which is an action, which is a number — that regex/keyword rules can't disentangle. This is real,
  AI-only value.
- **Classification — n/a** (rule-based; AI not used).
- **Verdict — AI is not the bottleneck.** The failure is the *verdict logic* (all-or-nothing matching) and
  period/unit alignment, not the model. The agent's AI value-add is therefore **limited to perception
  (reading the claim), not to the logic (judging it).**

## 5. Bottom line
The front end works reasonably and AI improves *perception*, but the **verdict stage almost never confirms
a true claim** (1/50; AUC 0.34) — and, crucially, **it won't do so even when the headline number matches
exactly** (NVIDIA), because the logic requires *every* number to match. That, plus comparing against the
wrong SEC reporting period, is the real weakness.

> **Human vs. agent.** A human analyst reads *"Q1 revenue of $81.62B, beating estimates of $79.18B,"*
> checks the $81.62B against the filing, and calls it **true** — knowing the $79.18B estimate isn't an
> official figure. The agent demands that *both* numbers match its evidence, so the one number official
> sources cannot contain drags a true claim down to "partially verified." The gap is judgment, not data.

## 6. Limitations & future work
- Verdict accuracy is evaluated on US-equity/macro claims the sources actually cover; opinion/forecast have
  no ground truth (we only check classification); crypto/exotic facts are out of scope.
- **Replace the hard-coded verdict rule with LLM reasoning.** The all-or-nothing matcher is brittle; an LLM
  judge could decide that "$81.62B matches; $79.18B is an estimate, not an official figure" and confirm the
  claim — exactly the judgment the rule lacks.
- **By design it verifies as-of-now.** *Usability improvement:* add **as-of-date** matching so dated/historical
  statements (e.g. *"the S&P 500 closed at 7,501.24 on May 15"*) are checked against that date rather than the
  latest value, plus **unit** matching (e.g. `units=pc1` for "rose X%").
- **Granularity matching (SEC):** read the claim's fiscal period (Q2 / half-year / FY) and pick the matching
  reporting window instead of an arbitrary one.
