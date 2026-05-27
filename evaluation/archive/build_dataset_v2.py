"""Build a v2 claim set aimed at the regime where AI *might* beat plain rules.

v1 tested exact numeric facts — a regime deterministic rules win outright. v2 adds
claims that need reading/reasoning, not a single-number lookup, so the AI judge gets
a fair chance to add value:

  direction   - "X's revenue increased / decreased year over year in fiscal Y."
                Truth = compare two real annual figures from SEC. The numeric check
                has no single figure to match, so it defers to the logic/AI judge.
  paraphrase  - the real figure restated as "approximately $N billion" (robustness:
                does the fixed check still work when the number is worded loosely?).

Every label is derived from real SEC figures. Output: evaluation/claims_v2.json
Usage: python3 evaluation/build_dataset_v2.py
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "JPM", "XOM"]
METRICS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net income": ["NetIncomeLoss"],
}
CONTACT = "FINM33200 selinaxian@uchicago.edu"
OUT_PATH = Path(__file__).resolve().parent / "claims_v2.json"


def _ctx() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_CTX = _ctx()


def _get_json(url: str, retries: int = 4) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": CONTACT})
        try:
            with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (403, 429) and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise last  # type: ignore[misc]


def ticker_to_cik() -> dict[str, int]:
    data = _get_json("https://www.sec.gov/files/company_tickers.json")
    return {str(r["ticker"]).upper(): int(r["cik_str"]) for r in data.values()}


def annual_values(facts: dict, concepts: list[str]) -> list[tuple[int, str]]:
    """(value, period_end) for full-year 10-K figures, newest first, deduped by end."""
    us = facts.get("facts", {}).get("us-gaap", {})
    by_end: dict[str, tuple[int, str]] = {}
    for concept in concepts:
        for e in us.get(concept, {}).get("units", {}).get("USD", []):
            if e.get("form") != "10-K" or e.get("val") is None:
                continue
            start, end = e.get("start"), e.get("end")
            if not start or not end:
                continue
            try:
                span = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except ValueError:
                continue
            if not (350 <= span <= 380):
                continue
            filed = e.get("filed", "")
            if end not in by_end or filed > by_end[end][1]:
                by_end[end] = (int(e["val"]), filed)
    return [(v[0], end) for end, v in sorted(by_end.items(), reverse=True)]


def build() -> list[dict]:
    cik_map = ticker_to_cik()
    rows: list[dict] = []
    for ticker in TICKERS:
        cik = cik_map.get(ticker)
        if cik is None:
            continue
        try:
            facts = _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        except Exception as exc:  # noqa: BLE001
            print(f"  [skip] {ticker}: {exc}")
            continue
        name = facts.get("entityName") or ticker
        for metric, concepts in METRICS.items():
            vals = annual_values(facts, concepts)
            if len(vals) < 2:
                continue
            (v0, end0), (v1, _) = vals[0], vals[1]
            if v0 == v1:
                continue
            year = end0[:4]
            grew = v0 > v1

            # direction: exactly one of increased/decreased is true
            rows.append({
                "ticker": ticker, "name": name, "metric": metric, "falsification": "direction",
                "label": "true" if grew else "false", "stated_value": None,
                "true_value": v0, "prior_value": v1,
                "claim": f"{name}'s annual {metric} increased year over year in fiscal {year} "
                         f"compared with the prior fiscal year.",
            })
            rows.append({
                "ticker": ticker, "name": name, "metric": metric, "falsification": "direction",
                "label": "false" if grew else "true", "stated_value": None,
                "true_value": v0, "prior_value": v1,
                "claim": f"{name}'s annual {metric} decreased year over year in fiscal {year} "
                         f"compared with the prior fiscal year.",
            })

            # paraphrase: real figure as "approximately $N billion" (true) vs a wrong one (false)
            b0 = v0 / 1e9
            wrong_b = round(b0 * 1.3, 1)
            rows.append({
                "ticker": ticker, "name": name, "metric": metric, "falsification": "paraphrase",
                "label": "true", "stated_value": round(b0, 1) * 1e9, "true_value": v0,
                "claim": f"{name}'s fiscal {year} annual {metric} was approximately ${b0:.1f} billion.",
            })
            rows.append({
                "ticker": ticker, "name": name, "metric": metric, "falsification": "paraphrase",
                "label": "false", "stated_value": wrong_b * 1e9, "true_value": v0,
                "claim": f"{name}'s fiscal {year} annual {metric} was approximately ${wrong_b:.1f} billion.",
            })
            print(f"  [ok] {ticker} {metric}: FY{year} {v0:,} vs prior {v1:,} ({'up' if grew else 'down'})")
        time.sleep(0.3)
    return rows


def main() -> None:
    print("Building v2 (direction + paraphrase) claim set...")
    rows = build()
    OUT_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    by = {}
    for r in rows:
        key = (r["falsification"], r["label"])
        by[key] = by.get(key, 0) + 1
    print(f"\nWrote {len(rows)} claims -> {OUT_PATH}")
    for k in sorted(by):
        print(f"   {k[0]:<12} {k[1]:<6} {by[k]}")


if __name__ == "__main__":
    main()
