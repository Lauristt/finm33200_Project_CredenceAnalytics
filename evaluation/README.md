# Evaluation — Credence Analytics

**Does the financial-claim verification agent work, and does AI help?** We test it on a
**real-news benchmark** (Yahoo Finance statements, labels verified against SEC/FRED) and measure
two things: can it *classify* a claim, and is its *true/false verdict* correct.

**One-line finding:** the front end works and AI lifts entity extraction (80.5% → 89.4%), but the
verdict stage confirms only **1 of 50** true claims and can't separate true from false (AUC 0.34).
Both error directions trace to one cause — **comparing the claim against the wrong moment**.

📄 Full write-up: **`EVALUATION_SUMMARY.md`** · audience page: **`../docs/index.html`** (EN) / `index.zh.html` (ZH)

---

## The dataset, in numbers
**113 statements** = **86 fact claims** (50 `true` / 36 `false`, used for the verdict test)
**+ 27 opinion/forecast/causal** (no truth value, used only for the classification test).

## Every number in the report → where it comes from

| Claim in the report | Number | Script | Result file | Scorecard |
|---|---|---|---|---|
| Entity / asset extraction | 80.5% → 89.4% | `eval_news.py` | `eval_news_results_heuristic.csv` (80.5) / `eval_news_results.csv` (89.4) | `scorecard_classification.txt` |
| Claim-type classification | 84.5% | `eval_news.py` | `eval_news_results.csv` | `scorecard_classification.txt` |
| Fact-check routing | 84.1% | `eval_news.py` | `eval_news_results.csv` | `scorecard_classification.txt` |
| Verdict accuracy | 36% (31/86) | `eval_verdict.py` | `results_news_verdict.csv` | `scorecard_verdict.txt` |
| True confirmed | 1/50 | `eval_verdict.py` | `results_news_verdict.csv` | `scorecard_verdict.txt` |
| False caught / missed | 30/36 caught, 6 missed | `eval_verdict.py` | `results_news_verdict.csv` | `scorecard_verdict.txt` |
| Confidence AUC | 0.34 | `eval_verdict.py` | `results_news_verdict.csv` | `scorecard_verdict.txt` |
| Failure taxonomy | per-claim buckets | `error_analysis.py` | `error_analysis_results.csv` | `scorecard_errors.txt` |

## Reproduce
```bash
cd credence_latest                                  # needs .env: OPENAI_API_KEY, FRED_API_KEY, SEC_USER_AGENT
PYTHONPATH=src python3 evaluation/eval_news.py      # classification (free, no LLM needed for the rule baseline)
python3 evaluation/eval_verdict.py                  # verdict  -> results_news_verdict.{csv,json}
python3 evaluation/error_analysis.py                # failure taxonomy -> error_analysis_results.csv
```

## Files
- `claims_news.json` / `.csv` / `.xlsx` — the benchmark (113 statements).
- `eval_news.py`, `eval_verdict.py`, `error_analysis.py` — the three evaluation scripts.
- `eval_news_results*.csv`, `results_news_verdict.{csv,json}`, `error_analysis_results.csv` — per-claim results.
- `scorecard_*.txt` — plain-text scorecards (the printed summaries).
- `EVALUATION_SUMMARY.md` — the write-up · `BUGS_FOUND.md` — bug report to the teammate · `AI_USAGE.md` — AI-usage statement.
- `archive/` — **abandoned directions** (constructed-data datasets, the Fix-A / routing experiments, and the
  pre-routing-fix baselines). Kept for provenance only — **not part of the final conclusions.**

> Note: `error_analysis_results.csv` is a supplementary per-claim taxonomy; the headline numbers come from
> `results_news_verdict.csv`. A fresh re-run may differ slightly (LLM non-determinism + the routing fix).
