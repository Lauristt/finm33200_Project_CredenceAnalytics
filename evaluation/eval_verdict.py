"""Verdict-accuracy evaluation on the teammate's pipeline.

Uses the SEC-anchored claim set (objective true/false labels) and reads the
pipeline's real per-claim verdict (atomic_claims[].verdict), then scores how
often that verdict matches the known truth.

Usage:
    python3 evaluation/eval_verdict.py                  # default claims.json
    CLAIMS_FILE=evaluation/claims_v2.json python3 evaluation/eval_verdict.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SEC_USER_AGENT", "FINM33200 selinaxian@uchicago.edu")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from financial_credibility import FinancialCredibilityToolkit  # noqa: E402
from financial_credibility import data_sources  # noqa: E402

CLAIMS = Path(os.getenv("CLAIMS_FILE") or (Path(__file__).resolve().parent / "claims.json"))

# her atomic verdict vocabulary -> a true/false-detection decision
CREDIBLE = {"supported"}
NOT_CREDIBLE = {"contradicted"}


def to_binary(verdict: str) -> str:
    if verdict in CREDIBLE:
        return "credible"
    if verdict in NOT_CREDIBLE:
        return "not_credible"
    return "uncertain"  # partially_supported / insufficient / not_applicable / etc.


def auc(true_scores, false_scores):
    if not true_scores or not false_scores:
        return float("nan")
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in true_scores for b in false_scores)
    return wins / (len(true_scores) * len(false_scores))


def cache_and_throttle(min_interval=0.2):
    orig = data_sources.FreeDataSourceClient._get_text
    cache, state = {}, {"last": 0.0}
    def patched(self, url, sec=False):
        if url in cache:
            return cache[url]
        wait = min_interval - (time.time() - state["last"])
        if wait > 0:
            time.sleep(wait)
        t = orig(self, url, sec=sec); state["last"] = time.time(); cache[url] = t
        return t
    data_sources.FreeDataSourceClient._get_text = patched


def run():
    claims = json.loads(CLAIMS.read_text(encoding="utf-8"))
    claims = [c for c in claims if c.get("label") in {"true", "false"}]  # fact-checkable only
    cache_and_throttle()
    tk = FinancialCredibilityToolkit.from_env()
    judge = type(tk.judge).__name__
    print(f"Verdict eval on {len(claims)} claims | judge={judge} | file={CLAIMS.name}\n")

    rows = []
    for i, c in enumerate(claims, 1):
        claim_text = c.get("claim") or c.get("statement", "")
        ticker = c.get("ticker") or c.get("entity", "")
        try:
            d = tk.build_evidence_pack(claim=claim_text, ticker=ticker,
                                       as_of_date="2026-05-25", max_sources=6, mode="strict").to_dict()
            acs = d.get("atomic_claims") or []
            fact = [a for a in acs if a.get("verdict") != "not_applicable"] or acs
            a0 = fact[0] if fact else {}
            verdict = a0.get("verdict", "insufficient")
            conf = float((a0.get("confidence_components") or {}).get("final_confidence", 0.0) or 0.0)
            review = bool(a0.get("human_review_required", False))
            deriv = a0.get("numeric_derivation") or {}
            reason = "; ".join(str(x) for x in (deriv.get("notes") or [])) or str(deriv.get("expression", ""))
        except Exception as exc:  # noqa: BLE001
            verdict, conf, review, reason = "ERROR", 0.0, True, str(exc)[:80]
        tb = to_binary(verdict)
        correct = tb == ("credible" if c["label"] == "true" else "not_credible")
        rows.append({**c, "verdict": verdict, "final_confidence": conf, "human_review": review,
                     "tool_binary": tb, "correct": correct, "reason": reason})
        grp_lbl = c.get("falsification") or c.get("asset_class") or "-"
        print(f"  [{i:>3}/{len(claims)}] {c['label']:<5} {grp_lbl:<14} -> {verdict}")

    tag = os.getenv("RUN_TAG") or "verdict"
    out_json = CLAIMS.parent / f"results_{tag}.json"
    out_csv = CLAIMS.parent / f"results_{tag}.csv"
    out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    cols = ["ticker", "falsification", "label", "stated_value", "true_value",
            "verdict", "tool_binary", "correct", "final_confidence", "human_review", "reason", "claim"]
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    report(rows, out_csv)


def report(rows, out_csv):
    trues = [r for r in rows if r["label"] == "true"]
    falses = [r for r in rows if r["label"] == "false"]
    n = len(rows)
    def pct(a, b):
        return f"{100*a/b:5.1f}%" if b else "  n/a"
    print("\n" + "=" * 60)
    print("VERDICT-ACCURACY SCORECARD")
    print("=" * 60)
    acc = sum(1 for r in rows if r["correct"])
    print(f"\n[1] Overall accuracy: {acc}/{n} ({pct(acc, n)})")
    print(f"    True  rated supported(credible):  {sum(1 for r in trues if r['tool_binary']=='credible')}/{len(trues)}")
    print(f"    False rated contradicted:         {sum(1 for r in falses if r['verdict']=='contradicted')}/{len(falses)}")
    a = auc([r["final_confidence"] for r in trues], [r["final_confidence"] for r in falses])
    print(f"\n[2] Confidence AUC (true vs false): {a:.3f}")
    print("\n[3] Accuracy by group (falsification type or asset class)")
    keyf = lambda r: r.get("falsification") or r.get("asset_class") or "-"
    for t in sorted({keyf(r) for r in rows}):
        grp = [r for r in rows if keyf(r) == t]
        print(f"    {t:<16}{sum(1 for r in grp if r['correct'])}/{len(grp)}")
    rev = [r for r in rows if r["human_review"]]
    rev_wrong = sum(1 for r in rev if not r["correct"])
    print(f"\n[4] Human-review flags: {len(rev)}/{n}; of those, wrong = {rev_wrong}/{len(rev) if rev else 0}")
    print(f"\nPer-claim -> {out_csv}")


if __name__ == "__main__":
    run()
