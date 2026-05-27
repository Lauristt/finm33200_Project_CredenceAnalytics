"""Evaluate the credibility toolkit on the SEC-anchored true/false claim set.

For every labeled claim we run the full toolkit pipeline live (real SEC data,
no API key) and ask one question: can the tool tell a true financial claim from
a false one?

We report three things the grading rubric asks for:
  1. Whether it works  -> numeric-verification accuracy, a threshold-free
     separation score (AUC), and a confusion matrix over the final label.
  2. A comparison to a simpler tool -> a "number-appears-in-evidence" baseline
     that sees the *same* retrieved evidence but uses a trivial decision rule.
  3. Failure cases -> the worst true/false misjudgements, with the evidence the
     tool actually saw.

Outputs: evaluation/results.json and a printed scorecard.

Usage:
    python3 evaluation/run_eval.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

# Identify ourselves to SEC before any toolkit network call happens.
os.environ.setdefault("SEC_USER_AGENT", "FINM33200 selinaxian@uchicago.edu")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from financial_credibility import FinancialCredibilityToolkit  # noqa: E402
from financial_credibility import data_sources  # noqa: E402
from financial_credibility.sources import extract_numbers  # noqa: E402

CLAIMS_PATH = Path(os.getenv("CLAIMS_FILE") or (Path(__file__).resolve().parent / "claims.json"))
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"

# Final labels the toolkit can emit, mapped to a binary "is this credible?" call.
CREDIBLE_LABELS = {"Very High", "High"}
NOT_CREDIBLE_LABELS = {"Low", "Contradicted"}  # "Medium" is treated as uncertain


def install_network_cache_and_throttle(min_interval: float = 0.2) -> None:
    """Wrap the toolkit's SEC/HTTP getter with a per-URL cache and a throttle.

    This does not change what the toolkit decides; it only avoids re-downloading
    the 1 MB SEC ticker map on every claim and keeps us under SEC's rate limit.
    """
    original = data_sources.FreeDataSourceClient._get_text
    cache: dict[str, str] = {}
    state = {"last": 0.0}

    def patched(self, url: str, sec: bool = False) -> str:
        if url in cache:
            return cache[url]
        wait = min_interval - (time.time() - state["last"])
        if wait > 0:
            time.sleep(wait)
        text = original(self, url, sec=sec)
        state["last"] = time.time()
        cache[url] = text
        return text

    data_sources.FreeDataSourceClient._get_text = patched


def to_binary(label: str) -> str:
    if label in CREDIBLE_LABELS:
        return "credible"
    if label in NOT_CREDIBLE_LABELS:
        return "not_credible"
    return "uncertain"


def baseline_number_in_evidence(stated_value, evidence) -> str:
    """Simpler tool: predict 'credible' iff the stated number is in the evidence."""
    if not stated_value:
        return "not_credible"  # no figure to look up (e.g. a directional claim)
    stated_value = int(stated_value)
    forms = {str(stated_value), f"{stated_value:,}"}
    # also a coarse "billions" form, e.g. 416161000000 -> 416.161
    billions = stated_value / 1_000_000_000
    forms.add(f"{billions:.3f}".rstrip("0").rstrip("."))
    forms.add(f"{billions:.1f}")
    for item in evidence:
        haystack = f"{item.title}\n{item.text}"
        nums = set(extract_numbers(haystack))
        nums_norm = {n.replace(",", "").replace("$", "").strip() for n in nums}
        if forms & nums_norm or any(f.replace(",", "") in haystack for f in forms):
            return "credible"
    return "not_credible"


def auc(true_scores: list[float], false_scores: list[float]) -> float:
    """Probability a random true claim scores above a random false one (Mann-Whitney)."""
    if not true_scores or not false_scores:
        return float("nan")
    wins = 0.0
    for t in true_scores:
        for f in false_scores:
            wins += 1.0 if t > f else 0.5 if t == f else 0.0
    return wins / (len(true_scores) * len(false_scores))


def classify_error(row: dict) -> str:
    """Bucket a verdict: '' if correct, else the kind of mistake."""
    want = "credible" if row["label"] == "true" else "not_credible"
    got = row["tool_binary"]
    if got == want:
        return ""
    if got == "uncertain":
        return "hedged_medium"   # tool refused to commit (Medium)
    if row["label"] == "true":
        return "true_rejected"   # real claim wrongly called not-credible
    return "false_passed"        # false claim wrongly called credible


def run() -> None:
    claims = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))
    install_network_cache_and_throttle()
    toolkit = FinancialCredibilityToolkit.from_env()
    judge_name = type(toolkit.judge).__name__
    uses_ai = judge_name != "HeuristicJudge"

    rows = []
    print(f"Running toolkit on {len(claims)} claims (live SEC) | judge = {judge_name} "
          f"({'AI' if uses_ai else 'no-AI'})\n")
    for i, c in enumerate(claims, 1):
        stated = c.get("stated_value", c["true_value"])  # what the claim actually asserts
        try:
            pack = toolkit.build_evidence_pack(
                claim=c["claim"],
                ticker=c["ticker"],
                as_of_date="2026-05-25",
                max_sources=6,
                mode="strict",
            )
            d = pack.to_dict()
            label = d["overall_conclusion"]["overall_label"]
            row = {
                **c,
                "stated_value": stated,
                "judge": judge_name,
                "overall_label": label,
                "final_confidence": d["overall_conclusion"]["final_confidence"],
                "numeric_verdict": d["numeric_check"]["verdict"],
                "reason": "; ".join(str(x) for x in d["numeric_check"].get("issues", [])),
                "n_evidence": len(d["evidence"]),
                "tool_binary": to_binary(label),
                "baseline_binary": baseline_number_in_evidence(stated, pack.evidence),
            }
        except Exception as exc:  # noqa: BLE001
            row = {**c, "stated_value": stated, "judge": judge_name, "error": str(exc),
                   "overall_label": "ERROR", "final_confidence": 0.0,
                   "numeric_verdict": "error", "reason": f"error: {exc}", "n_evidence": 0,
                   "tool_binary": "uncertain", "baseline_binary": "not_credible"}
        row["correct"] = row["tool_binary"] == ("credible" if c["label"] == "true" else "not_credible")
        row["error_type"] = classify_error(row)
        rows.append(row)
        print(f"  [{i:>2}/{len(claims)}] {c['label']:<5} {c['ticker']:<5} "
              f"{c['falsification']:<13} -> {row['overall_label']:<12} "
              f"numeric={row['numeric_verdict']}")

    # Name outputs by run tag (e.g. RUN_TAG=ai_fixed) so AI / no-AI runs don't clobber.
    tag = os.getenv("RUN_TAG") or judge_name
    out_json = CLAIMS_PATH.parent / f"results_{tag}.json"
    out_csv = CLAIMS_PATH.parent / f"results_{tag}.csv"
    out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    RESULTS_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(rows, out_csv)
    report(rows, out_json, out_csv)


def _write_csv(rows: list[dict], path: Path) -> None:
    """One traceable row per claim, so every single judgement can be inspected."""
    cols = ["ticker", "metric", "falsification", "label", "stated_value", "true_value",
            "overall_label", "numeric_verdict", "final_confidence", "tool_binary",
            "correct", "error_type", "reason", "claim"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in cols})


def report(rows: list[dict], out_json: Path = RESULTS_PATH, out_csv: Path | None = None) -> None:
    trues = [r for r in rows if r["label"] == "true"]
    falses = [r for r in rows if r["label"] == "false"]
    cats = ["number_big", "number_small", "wrong_company", "wrong_time"]

    def pct(n, d):
        return f"{100*n/d:4.0f}%" if d else "  n/a"

    print("\n" + "=" * 64)
    print("SCORECARD")
    print("=" * 64)

    # 1) Headline feature: numeric verification
    true_verified = sum(1 for r in trues if r["numeric_verdict"] == "verified")
    false_flagged = sum(1 for r in falses if r["numeric_verdict"] in {"contradicted", "not_found", "insufficient"})
    false_contradicted = sum(1 for r in falses if r["numeric_verdict"] == "contradicted")
    print("\n[1] Numeric verification (the core feature)")
    print(f"    True claims correctly VERIFIED:        {true_verified}/{len(trues)}  ({pct(true_verified, len(trues))})")
    print(f"    False claims correctly NOT verified:   {false_flagged}/{len(falses)}  ({pct(false_flagged, len(falses))})")
    print(f"    False claims explicitly CONTRADICTED:  {false_contradicted}/{len(falses)}  ({pct(false_contradicted, len(falses))})")

    # 2) Threshold-free separation
    a = auc([r["final_confidence"] for r in trues], [r["final_confidence"] for r in falses])
    mean_t = sum(r["final_confidence"] for r in trues) / len(trues) if trues else 0
    mean_f = sum(r["final_confidence"] for r in falses) / len(falses) if falses else 0
    print("\n[2] Overall-confidence separation (true vs false)")
    print(f"    Mean confidence  true={mean_t:.3f}   false={mean_f:.3f}")
    print(f"    AUC (1.0=perfect, 0.5=coin flip):      {a:.3f}")

    # 3) Final-label confusion
    print("\n[3] Final label distribution")
    print(f"    {'label':<12}{'true claims':>13}{'false claims':>14}")
    for lab in ["Very High", "High", "Medium", "Low", "Contradicted", "ERROR"]:
        nt = sum(1 for r in trues if r["overall_label"] == lab)
        nf = sum(1 for r in falses if r["overall_label"] == lab)
        if nt or nf:
            print(f"    {lab:<12}{nt:>13}{nf:>14}")

    # 4) Tool vs simpler baseline (binary accuracy, 'uncertain' counts as wrong)
    def acc(key):
        correct = sum(1 for r in rows
                      if r[key] == ("credible" if r["label"] == "true" else "not_credible"))
        return correct, len(rows)

    tool_c, n = acc("tool_binary")
    base_c, _ = acc("baseline_binary")
    print("\n[4] Tool vs simpler baseline  (accuracy on true/false detection)")
    print(f"    Toolkit (full pipeline):               {tool_c}/{n}  ({pct(tool_c, n)})")
    print(f"    Baseline (number-in-evidence only):    {base_c}/{n}  ({pct(base_c, n)})")
    print(f"    Trivial (always 'credible'):           {len(trues)}/{n}  ({pct(len(trues), n)})")

    # 5) LAYER 1 — accuracy per claim type (works for v1 and v2 datasets)
    print("\n[5] LAYER 1 - accuracy by claim type")
    print(f"    {'type':<15}{'n':>4}{'correct':>10}{'AUC':>9}")
    true_scores = [r["final_confidence"] for r in trues]
    types: list[str] = []
    for r in rows:
        t = r.get("falsification", "?")
        if t not in types:
            types.append(t)
    for t in types:
        grp = [r for r in rows if r.get("falsification", "?") == t]
        correct = sum(1 for r in grp if r["correct"])
        gt = [r["final_confidence"] for r in grp if r["label"] == "true"]
        gf = [r["final_confidence"] for r in grp if r["label"] == "false"]
        if gt and gf:
            a_str = f"{auc(gt, gf):>9.3f}"          # within-type separation (v2)
        elif gf:
            a_str = f"{auc(true_scores, gf):>9.3f}"  # false-only type vs the true set (v1)
        else:
            a_str = "    --   "
        print(f"    {t:<15}{len(grp):>4}{correct:>4}/{len(grp):<4}{a_str}")

    # 6) LAYER 2 — what kinds of mistakes were made
    print("\n[6] LAYER 2 - error breakdown")
    wrong = [r for r in rows if r["error_type"]]
    print(f"    correct:               {len(rows) - len(wrong)}/{len(rows)}")
    for et, desc in [("false_passed", "false claim called credible"),
                     ("true_rejected", "true claim called not-credible"),
                     ("hedged_medium", "tool hedged with 'Medium'")]:
        c = sum(1 for r in wrong if r["error_type"] == et)
        if c:
            print(f"    {et:<22}{c:<4}({desc})")

    # 7) LAYER 3 — full traceable table
    print("\n[7] LAYER 3 - every claim is traceable in:")
    if out_csv:
        print(f"    {out_csv}   (open in Excel)")
    print(f"    {out_json}   (full JSON)")
    examples = [r for r in rows if r["error_type"]][:3]
    if examples:
        print("    sample wrong rows:")
        for r in examples:
            print(f"      {r['ticker']:<5} {r['falsification']:<13} truth={r['label']:<5} "
                  f"-> {r['overall_label']:<12} [{r['error_type']}] {r['reason'][:55]}")


if __name__ == "__main__":
    run()
