"""Failure taxonomy: WHY did the pipeline fail to confirm true claims?

Runs each true, fact-checkable news claim through the pipeline, captures internal
signals (entity extraction, classification, evidence count, numeric/atomic verdict),
and buckets every non-confirmation into a distinct failure mode — so we can report
how the errors actually formed instead of assuming a single cause.

Run it on the PRE-FIX code (revert data_sources.py first) to analyze the original
errors. Output: evaluation/error_analysis_results.csv + a printed taxonomy.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("SEC_USER_AGENT", "FINM33200 selinaxian@uchicago.edu")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from financial_credibility import FinancialCredibilityToolkit, data_sources  # noqa: E402
from financial_credibility.argument import classify_argument_type  # noqa: E402
from financial_credibility.entity_extraction import extract_entities_from_memo  # noqa: E402

DATA = Path(__file__).resolve().parent / "claims_news.json"

ASSET_MAP = {"stock": "single_name_equity", "macro": "macro_indicator", "commodity": "commodity",
             "fx": "fx", "index": "equity_index", "rates": "rates", "crypto": "crypto"}
# segment / non-top-line metrics that the SEC concept map does not expose as a simple fact
SEGMENT_RE = re.compile(
    r"\b(iphone|aws|data ?center|greater china|services|cloud|earnings per share|"
    r"per share|\beps\b|net interest income|operating income|gross margin)\b", re.I)

BUCKET_NAMES = {
    "A_period_or_escalation": "A. Period coverage / over-escalation (the Fix A class)",
    "B_concept_gap":          "B. Concept-mapping gap (segment metric / EPS not a mapped concept)",
    "C_no_evidence":          "C. No evidence retrieved (routing / data-source miss)",
    "D_entity_miss":          "D. Entity / asset-class not extracted",
    "E_classified_skip":      "E. Classified as non-factual and skipped",
    "uncategorized":          "uncategorized",
}


def cache_throttle(min_interval: float = 0.2) -> None:
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


def attribute(r: dict) -> str:
    """Bucket a non-confirmed true claim into one failure mode (priority order)."""
    if not r["entity_ok"]:
        return "D_entity_miss"
    if r["n_evidence"] == 0:
        return "C_no_evidence"
    if r["segment_metric"]:
        return "B_concept_gap"
    if r["atomic_verdict"] == "not_applicable":
        return "E_classified_skip"
    if r["atomic_verdict"] == "contradicted" or r["numeric_verdict"] in {"not_found", "insufficient"}:
        return "A_period_or_escalation"
    return "uncategorized"


def run() -> None:
    claims = [c for c in json.loads(DATA.read_text(encoding="utf-8")) if c.get("label") == "true"]
    cache_throttle()
    tk = FinancialCredibilityToolkit.from_env()
    print(f"Analyzing {len(claims)} TRUE claims | judge={type(tk.judge).__name__}\n")
    rows = []
    for i, c in enumerate(claims, 1):
        s, ent = c["statement"], c.get("entity", "")
        detected = set(extract_entities_from_memo(s, tk.config).get("asset_classes", []))
        entity_ok = ASSET_MAP.get(c["asset_class"]) in detected
        arg = classify_argument_type(s).argument_type.value
        try:
            d = tk.build_evidence_pack(claim=s, ticker=ent, as_of_date="2026-05-25",
                                       max_sources=6, mode="strict").to_dict()
            n_ev = len(d["evidence"])
            num_v = d["numeric_check"]["verdict"]
            atomic_v = (d.get("atomic_claims") or [{}])[0].get("verdict", "?")
        except Exception as exc:  # noqa: BLE001
            n_ev, num_v, atomic_v = 0, "error", f"error:{str(exc)[:40]}"
        row = {**c, "entity_ok": entity_ok, "arg_type": arg, "n_evidence": n_ev,
               "numeric_verdict": num_v, "atomic_verdict": atomic_v,
               "segment_metric": bool(SEGMENT_RE.search(s)),
               "confirmed": atomic_v == "supported"}
        row["bucket"] = "" if row["confirmed"] else attribute(row)
        rows.append(row)
        print(f"  [{i:>2}/{len(claims)}] {c['asset_class']:<9} ev={n_ev} "
              f"{atomic_v:<16} {BUCKET_NAMES.get(row['bucket'], row['bucket'])[:34]}")
    report(rows)
    cols = ["id", "asset_class", "claim_type", "entity", "statement", "entity_ok", "arg_type",
            "n_evidence", "numeric_verdict", "atomic_verdict", "segment_metric", "confirmed", "bucket"]
    out = DATA.parent / "error_analysis_results.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    print(f"\nPer-claim -> {out}")


def report(rows: list[dict]) -> None:
    fails = [r for r in rows if not r["confirmed"]]
    confirmed = len(rows) - len(fails)
    print("\n" + "=" * 62)
    print(f"FAILURE TAXONOMY — true claims confirmed {confirmed}/{len(rows)}; "
          f"{len(fails)} failed and were attributed below")
    print("=" * 62)
    by = Counter(r["bucket"] for r in fails)
    for b, n in by.most_common():
        print(f"\n  {BUCKET_NAMES.get(b, b)}  —  {n} claims")
        for ex in [r for r in fails if r["bucket"] == b][:3]:
            print(f"     · [{ex['asset_class']}] {ex['statement'][:58]}  "
                  f"(ev={ex['n_evidence']}, {ex['atomic_verdict']})")
    print("\nReading: if multiple buckets are non-trivial, the pre-fix errors had MULTIPLE")
    print("distinct causes — Fix A only addressed bucket A.")


if __name__ == "__main__":
    run()
