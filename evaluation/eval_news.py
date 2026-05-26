"""Evaluate the pipeline's classification stages on the Yahoo-news claim set.

Checks three capabilities that need no data API key (they run before retrieval):
  A) entity / asset-class extraction  - does it find the right entity & asset class?
  B) claim-type classification         - factual/numeric/opinion/forecast?
  C) fact-check routing                - are opinion/forecast correctly NOT fact-checked?

Verdict accuracy (does it judge true vs false) is handled separately for the
stock subset (SEC-checkable) in run_eval.py; macro/commodity/fx verdicts need a
FRED key and are flagged as a coverage limitation.

Usage:  python3 evaluation/eval_news.py        (set OPENAI_API_KEY= to force
heuristic-only entity extraction; leave the key set to add the LLM layer.)
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("SEC_USER_AGENT", "FINM33200 selinaxian@uchicago.edu")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from financial_credibility.argument import classify_argument_type  # noqa: E402
from financial_credibility.config import ToolkitConfig  # noqa: E402
from financial_credibility.entity_extraction import extract_entities_from_memo  # noqa: E402

DATA = Path(__file__).resolve().parent / "claims_news.json"

# my asset_class label -> the pipeline's asset_class vocabulary
ASSET_MAP = {
    "stock": "single_name_equity", "macro": "macro_indicator", "commodity": "commodity",
    "fx": "fx", "index": "equity_index", "rates": "rates", "crypto": "crypto",
}
# my claim_type label -> the argument types that count as a correct classification
TYPE_MAP = {
    "numeric": {"metric_fact"},
    "factual": {"event_fact", "attribution_fact", "metric_fact"},
    "opinion": {"opinion_analysis"},
    "forecast": {"forecast"},
    "causal": set(),  # her classifier has no causal type -> scored separately, not in accuracy
}
FACTUAL_TYPES = {"metric_fact", "event_fact", "attribution_fact"}


def pct(n, d):
    return f"{100*n/d:5.1f}%" if d else "  n/a"


def run() -> None:
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    cfg = ToolkitConfig.from_env()
    uses_llm = bool(cfg.openai_api_key)
    print(f"Entity extraction mode: {'heuristic + LLM' if uses_llm else 'heuristic only'}\n")

    out = []
    for r in rows:
        s = r["statement"]
        ee = extract_entities_from_memo(s, cfg)
        detected_classes = set(ee.get("asset_classes", []))
        top = ee.get("entities", [{}])[0] if ee.get("entities") else {}
        arg = classify_argument_type(s).argument_type.value

        expected_class = ASSET_MAP.get(r["asset_class"])
        entity_ok = expected_class in detected_classes

        targets = TYPE_MAP.get(r["claim_type"], set())
        class_ok = arg in targets if targets else None  # None for causal (no target)

        should_check = r["claim_type"] in {"numeric", "factual", "causal"}  # has truth / checkable
        is_checked = arg in FACTUAL_TYPES
        route_ok = (is_checked == should_check)

        out.append({**r,
                    "detected_asset_classes": "|".join(sorted(detected_classes)) or "(none)",
                    "detected_entity": top.get("name", ""),
                    "argument_type": arg,
                    "entity_ok": entity_ok, "class_ok": class_ok, "route_ok": route_ok})

    report(out)
    cols = ["id", "statement", "asset_class", "claim_type", "label",
            "detected_asset_classes", "detected_entity", "argument_type",
            "entity_ok", "class_ok", "route_ok"]
    csv_path = DATA.parent / "eval_news_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"\nPer-statement results -> {csv_path}")


def report(out: list[dict]) -> None:
    n = len(out)
    print("=" * 60)
    print(f"NEWS-CLAIM CLASSIFICATION SCORECARD  ({n} statements)")
    print("=" * 60)

    # A) entity / asset-class extraction
    eok = sum(1 for r in out if r["entity_ok"])
    print(f"\n[A] Entity / asset-class extraction:  {eok}/{n}  ({pct(eok, n)})")
    print(f"    {'asset class':<12}{'n':>4}{'found':>10}")
    for ac in sorted({r["asset_class"] for r in out}):
        grp = [r for r in out if r["asset_class"] == ac]
        ok = sum(1 for r in grp if r["entity_ok"])
        print(f"    {ac:<12}{len(grp):>4}{ok:>4}/{len(grp):<4}")

    # B) claim-type classification (where a target exists)
    scored = [r for r in out if r["class_ok"] is not None]
    cok = sum(1 for r in scored if r["class_ok"])
    print(f"\n[B] Claim-type classification:  {cok}/{len(scored)}  ({pct(cok, len(scored))})")
    print("    (causal excluded: the pipeline has no 'causal' class)")
    print(f"    {'my type':<10}{'n':>4}{'correct':>10}")
    for ct in ["numeric", "factual", "opinion", "forecast"]:
        grp = [r for r in out if r["claim_type"] == ct]
        ok = sum(1 for r in grp if r["class_ok"])
        if grp:
            print(f"    {ct:<10}{len(grp):>4}{ok:>4}/{len(grp):<4}")

    # C) fact-check routing
    rok = sum(1 for r in out if r["route_ok"])
    opi = [r for r in out if r["claim_type"] in {"opinion", "forecast"}]
    opi_ok = sum(1 for r in opi if r["argument_type"] in {"opinion_analysis", "forecast"})
    fac = [r for r in out if r["claim_type"] in {"numeric", "factual", "causal"}]
    fac_ok = sum(1 for r in fac if r["argument_type"] in FACTUAL_TYPES)
    print(f"\n[C] Fact-check routing:  {rok}/{n}  ({pct(rok, n)})")
    print(f"    opinion/forecast correctly NOT fact-checked: {opi_ok}/{len(opi)}  ({pct(opi_ok, len(opi))})")
    print(f"    factual/numeric/causal correctly fact-checked: {fac_ok}/{len(fac)}  ({pct(fac_ok, len(fac))})")


if __name__ == "__main__":
    run()
