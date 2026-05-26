# AI Usage Statement

Two distinct uses of AI in this project — one as a **tool we used to build the
evaluation**, and one as the **system component we were evaluating**. We keep them
separate below.

## 1. AI as the system under test (the subject)

The Credence Analytics pipeline itself uses an LLM (**OpenAI `gpt-4o-mini`**, via an
OpenAI-compatible endpoint) for entity extraction and as a semantic judge. This is the
thing we evaluated, not a tool we used for analysis. Our evaluation explicitly measures
whether this LLM component adds value (e.g., entity extraction rules 80.5% → 89.4% with
the LLM layer).

## 2. AI as a tool we used (Claude Code / Claude)

We used **Claude (via Claude Code)** as a coding/research assistant to build and run the
evaluation. Specifically, Claude helped:

- **Build the benchmark:** pull real statements from Yahoo Finance, organize them by asset
  class and claim type, and generate matched true/false pairs via number/date perturbation
  (`claims_news.json`, `claims.json`).
- **Write the evaluation harness:** `eval_news.py`, `eval_verdict.py`, `build_dataset*.py`,
  `compare.py`, and the per-claim CSV/Excel exports.
- **Diagnose the verdict bug:** trace the pipeline, dump intermediate outputs, and locate the
  `sec_company_facts` truncation as the root cause.
- **Implement Fix A** and re-run the before/after comparison.
- **Draft documentation:** `EVALUATION_SUMMARY.md`, `BUGS_FOUND.md`, and this statement.

## How we checked the AI's outputs

We did not take AI output on trust. In particular:

- **Ground-truth labels were verified against primary sources.** Every "true" numeric claim
  was cross-checked against **SEC EDGAR** (company filings) or **FRED** (macro/market data) —
  not against anything an LLM produced. When the pipeline disagreed with a label, we went to
  SEC to adjudicate (e.g., we confirmed Apple Q2 = $111,184M and NVIDIA Q1 = $81,615M in SEC,
  proving the labels right and the pipeline wrong).
- **All numbers in this report are reproducible** by running the scripts on the committed
  data; we inspected the per-claim `results_*.csv` rather than trusting summary claims.
- **The bug diagnosis was confirmed by reading the source code** and dumping the pipeline's
  internal `canonical_facts` / `numeric_check` / `verdict`, not inferred from an LLM summary.
- **Perturbed (false) labels are correct by construction** (we changed a known-true figure),
  so they need no external trust.
- Where an LLM summarized news figures, we treated those as candidates and re-verified the
  numbers against SEC/FRED before labeling.

## Keys / secrets

API keys (OpenAI, FRED) are kept in a local `.env` file, which is gitignored and **not part
of the submission**.
