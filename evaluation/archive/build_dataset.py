"""Build a *categorized* labeled claim dataset from real SEC EDGAR filings.

Every figure is a real value pulled from the SEC XBRL companyfacts API (free, no
key), so labels are objective and reproducible. For each company/metric we emit
one true claim and four kinds of false claim, each probing a different ability:

  true          - the real figure for the real period.
  number_big    - figure changed by ~+50% / -45%  (gross magnitude error).
  number_small  - figure changed by ~+4% / -4%    (subtle precision error).
  wrong_company - this company's claim stated with ANOTHER company's real figure
                  (tests entity binding).
  wrong_time    - a real figure of this company, but stated for the WRONG fiscal
                  year/date (tests period binding).

Only the targeted detail differs between a true claim and its false variants;
sentence wording is otherwise identical, so the test isolates one skill at a time.

Output: evaluation/claims.json   Usage: python3 evaluation/build_dataset.py
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "JPM", "XOM"]

METRICS = {
    "annual revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "annual net income": ["NetIncomeLoss"],
}

CONTACT = "FINM33200 selinaxian@uchicago.edu"
OUT_PATH = Path(__file__).resolve().parent / "claims.json"


def _ctx() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_CTX = _ctx()


def _get_json(url: str, retries: int = 4) -> dict:
    last_exc: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": CONTACT})
        try:
            with urllib.request.urlopen(request, timeout=30, context=_CTX) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (403, 429) and attempt < retries - 1:
                wait = 3 * (attempt + 1)
                print(f"    SEC {exc.code}; backing off {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise last_exc  # type: ignore[misc]


def ticker_to_cik() -> dict[str, int]:
    data = _get_json("https://www.sec.gov/files/company_tickers.json")
    return {str(r["ticker"]).upper(): int(r["cik_str"]) for r in data.values()}


def annual_values(facts: dict, concepts: list[str]) -> list[tuple[int, str, str]]:
    """All full-year (10-K) USD values as (value, period_end, fiscal_year), newest first.

    De-duplicated by period_end, keeping the most recently filed value for each
    period so restatements win over originals.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    by_end: dict[str, tuple[int, str, str]] = {}  # end -> (val, fy, filed)
    for concept in concepts:
        for e in us_gaap.get(concept, {}).get("units", {}).get("USD", []):
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
            prev = by_end.get(end)
            if prev is None or filed > prev[2]:
                by_end[end] = (int(e["val"]), str(e.get("fy", "")), filed)
    return [(v[0], end, v[1]) for end, v in sorted(by_end.items(), reverse=True)]


def perturb_big(v: int) -> int:
    return int(round(v * (1.5 if v % 2 == 0 else 0.55), -6))


def perturb_small(v: int) -> int:
    out = int(round(v * (1.04 if v % 2 == 0 else 0.96), -6))
    return out if out != v else out + 1_000_000


CLAIM = "{name} reported {metric} of {value} for the fiscal year ending {period}."


def build() -> list[dict]:
    cik_map = ticker_to_cik()

    # Phase 1: collect real annual series per (ticker, metric).
    series: dict[tuple[str, str], dict] = {}
    for ticker in TICKERS:
        cik = cik_map.get(ticker)
        if cik is None:
            print(f"  [skip] {ticker}: not in SEC map")
            continue
        try:
            facts = _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        except Exception as exc:  # noqa: BLE001
            print(f"  [skip] {ticker}: {exc}")
            time.sleep(0.5)
            continue
        name = facts.get("entityName") or ticker
        for metric, concepts in METRICS.items():
            vals = annual_values(facts, concepts)
            if vals:
                series[(ticker, metric)] = {"name": name, "values": vals}
        time.sleep(0.3)

    rows: list[dict] = []
    for (ticker, metric), info in series.items():
        name, vals = info["name"], info["values"]
        v0, p0, _ = vals[0]                       # latest annual value
        prior = next(((v, p) for v, p, _ in vals[1:] if v != v0), None)  # a different period

        # donor = company with the most different value for the same metric
        donor = None
        for (t2, m2), info2 in series.items():
            if m2 != metric or t2 == ticker:
                continue
            dv = info2["values"][0][0]
            if abs(dv - v0) / max(v0, 1) < 0.15:
                continue
            if donor is None or abs(dv - v0) > abs(donor - v0):
                donor = dv

        def add(value, label, falsification, true_value, period=p0):
            rows.append({
                "ticker": ticker, "name": name, "metric": metric,
                "period_end": period, "true_value": true_value,
                "stated_value": value, "label": label,
                "falsification": falsification,
                "claim": CLAIM.format(name=name, metric=metric, value=value, period=period),
            })

        add(v0, "true", "none", v0)
        add(perturb_big(v0), "false", "number_big", v0)
        add(perturb_small(v0), "false", "number_small", v0)
        if donor is not None:
            add(donor, "false", "wrong_company", v0)
        if prior is not None:
            pv, pp = prior
            # state the latest figure v0 against an earlier period whose real value was pv
            add(v0, "false", "wrong_time", pv, period=pp)
        print(f"  [ok] {ticker} {metric}: real={v0:,} @ {p0}")
    return rows


def main() -> None:
    print("Building categorized SEC-anchored claim dataset...")
    rows = build()
    OUT_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    by_cat: dict[str, int] = {}
    for r in rows:
        by_cat[r["falsification"]] = by_cat.get(r["falsification"], 0) + 1
    print(f"\nWrote {len(rows)} claims -> {OUT_PATH}")
    for cat, n in sorted(by_cat.items()):
        print(f"   {cat:<14} {n}")


if __name__ == "__main__":
    main()
