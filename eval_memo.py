#!/usr/bin/env python3
"""
eval_memo.py — headless eval tool for CredenceAnalytics.

Submits a memo directly to the backend (no HTTP, no browser) and prints a
compact, readable text report.  Designed so the assistant can read the output
and immediately identify what to fix.

Usage
-----
  # Inline memo:
  python eval_memo.py --ticker SPX --date 2025-05-16 --memo "S&P 500 rose 2.3% last week..."

  # Memo from file:
  python eval_memo.py --ticker SPX --date 2025-05-16 --file my_memo.txt

  # Multiple tickers (space-separated):
  python eval_memo.py --ticker WTI BRENT DGS10 FEDFUNDS CPI --date 2025-05-16 --file macro.txt

  # Show full derivation inputs:
  python eval_memo.py --ticker AAPL --date 2025-03-28 --file memo.txt --verbose
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from typing import Any

# ── Bootstrap path so we can import from src/ without install ────────────────
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from financial_credibility.config import ToolkitConfig
from financial_credibility.reporting import build_verification_report


# ── Verdict colour codes (terminal) ─────────────────────────────────────────
_VERDICT_SYMBOLS = {
    "supported": "✓  SUPPORTED",
    "verified": "✓  VERIFIED",
    "partially_verified": "~  PARTIAL",
    "contradicted": "✗  CONTRADICTED",
    "insufficient": "?  INSUFFICIENT",
    "not_applicable": "—  N/A",
    "error": "!  ERROR",
}


def _verdict_label(v: str) -> str:
    return _VERDICT_SYMBOLS.get((v or "").lower(), f"?  {v.upper()}")


def _short(text: str, width: int = 120) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width] + "…"


def _derivation_line(d: dict[str, Any] | None) -> str:
    if not d:
        return ""
    expr = d.get("expression") or "?"
    inp = d.get("inputs") or {}
    passed = d.get("passed")
    result = d.get("result")
    threshold = d.get("threshold")
    comparator = d.get("comparator") or "~="
    tolerance = d.get("tolerance")
    passed_str = "PASS" if passed is True else "FAIL" if passed is False else "?"

    if expr == "level_check":
        actual = inp.get("actual", result)
        claimed = inp.get("claimed", threshold)
        diff_pct = inp.get("diff_pct")
        tol_str = f" tol={int((tolerance or 0)*100)}%" if tolerance is not None else ""
        diff_str = f" diff={diff_pct*100:.1f}%" if diff_pct is not None else ""
        return f"level_check | actual={actual} vs claimed={claimed}{diff_str}{tol_str} | {passed_str}"

    if expr in {"ratio_check", "growth_check", "yoy_growth", "qoq_growth"}:
        current = inp.get("current", inp.get("numerator"))
        prior = inp.get("prior", inp.get("denominator"))
        period = inp.get("current_period") or inp.get("period") or ""
        prior_period = inp.get("prior_period") or ""
        result_pct = f"{float(result)*100:.2f}%" if result is not None else "?"
        thresh_pct = f"{float(threshold)*100:.2f}%" if threshold is not None else "?"
        period_str = f" [{prior_period} → {period}]" if prior_period else f" [{period}]"
        return f"{expr} | {current} / {prior}{period_str} = {result_pct} {comparator} {thresh_pct} | {passed_str}"

    # Generic fallback
    result_str = f"{float(result)*100:.2f}%" if isinstance(result, float) and 0 < abs(result) < 10 else str(result)
    thresh_str = f"{float(threshold)*100:.2f}%" if isinstance(threshold, float) and 0 < abs(threshold) < 10 else str(threshold)
    return f"{expr} | result={result_str} {comparator} {thresh_str} | {passed_str}"


def _source_line(result: dict[str, Any], evidence_lookup: dict[str, dict]) -> str:
    urls = result.get("evidence_urls") or []
    keys = result.get("evidence_keys") or []
    for url in urls:
        ev = evidence_lookup.get(url)
        if ev:
            title = ev.get("title") or url
            tier = ev.get("source_tier") or ""
            official = "✓official" if ev.get("is_official_primary") else ""
            return f"{_short(title, 80)}  [{tier}{' ' if tier and official else ''}{official}]"
    if keys:
        return keys[0]
    return "(no source)"


def _format_report(payload: dict[str, Any], verbose: bool = False) -> str:
    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    inp = payload.get("input") or {}
    lines.append("=" * 72)
    lines.append(f"  CredenceAnalytics Eval  |  date: {inp.get('as_of_date') or '?'}")
    lines.append(f"  tickers: {', '.join(inp.get('tickers') or [])}")
    lines.append(f"  memo: {_short(inp.get('memo') or '', 80)}")
    lines.append("=" * 72)

    # ── Entity runs ──────────────────────────────────────────────────────────
    runs = payload.get("runs") or []
    if not runs:
        lines.append("  (no entity runs found in payload)")
        lines.append("")

    for run in runs:
        ticker = run.get("ticker") or run.get("entity_name") or "?"
        entity_name = run.get("entity_name") or ticker
        asset_class = run.get("asset_class") or run.get("claim_type") or ""
        overall = run.get("verdict") or run.get("credibility_label") or "?"

        lines.append("")
        lines.append(f"┌── ENTITY: {entity_name} ({ticker})  [{asset_class}]  overall={overall.upper()}")

        # Build evidence lookup for this run
        evidence_lookup: dict[str, dict] = {}
        for ev in run.get("evidence") or []:
            url = ev.get("url") or ""
            if url:
                evidence_lookup[url] = ev

        # Atomic claims
        atomic_claims = run.get("atomic_claims") or []
        if not atomic_claims:
            lines.append("│   (no atomic claims)")
        for ac_result in atomic_claims:
            ac = ac_result.get("atomic_claim") or {}
            claim_text = ac.get("text") or ""
            arg_type = ac.get("argument_type") or ""
            verdict = ac_result.get("verdict") or "?"
            confidence_comp = ac_result.get("confidence_components") or {}
            confidence = confidence_comp.get("final_confidence")
            human_review = ac_result.get("human_review_required") or False
            review_reasons = ac_result.get("review_reasons") or []
            derivation = ac_result.get("numeric_derivation")
            issues = [i for i in (ac_result.get("issues") or []) if i and "http error" not in str(i).lower()]

            conf_str = f"  conf={confidence:.2f}" if confidence is not None else ""
            review_str = "  ⚑ REVIEW" if human_review else ""
            lines.append("│")
            lines.append(f"│  Claim:   {_short(claim_text, 100)}")
            lines.append(f"│  Type:    {arg_type}")
            lines.append(f"│  Verdict: {_verdict_label(verdict)}{conf_str}{review_str}")

            deriv_str = _derivation_line(derivation)
            if deriv_str:
                lines.append(f"│  Deriv:   {deriv_str}")

            source_str = _source_line(ac_result, evidence_lookup)
            lines.append(f"│  Source:  {source_str}")

            if review_reasons:
                lines.append(f"│  Review:  {', '.join(review_reasons)}")
            if issues:
                lines.append(f"│  Issues:  {', '.join(str(i) for i in issues[:3])}")

            # LLM summaries (if present)
            llm_src = ac_result.get("llm_source_summary") or ""
            llm_match = ac_result.get("llm_match_summary") or ""
            if verbose and llm_src:
                lines.append(f"│  LLM-src: {_short(llm_src, 100)}")
            if verbose and llm_match:
                lines.append(f"│  LLM-why: {_short(llm_match, 100)}")

            # Verbose: full derivation inputs
            if verbose and derivation:
                inp_dict = derivation.get("inputs") or {}
                if inp_dict:
                    lines.append(f"│  Drv-inp: {inp_dict}")

        # Canonical facts (verbose mode)
        if verbose:
            facts = run.get("canonical_facts") or []
            if facts:
                lines.append("│")
                lines.append(f"│  Canonical facts ({len(facts)} total, showing first 5):")
                for f in facts[:5]:
                    fname = f.get("fact_name") or f.get("fact_id") or "?"
                    fval = f.get("value")
                    fperiod = f.get("report_period") or f.get("observation_date") or ""
                    lines.append(f"│    {fname}  =  {fval}  [{fperiod}]")

        lines.append("└" + "─" * 68)

    # ── Summary ──────────────────────────────────────────────────────────────
    summary = payload.get("summary") or {}
    lines.append("")
    lines.append(f"Summary:")
    for k, v in summary.items():
        if k.startswith("_") or isinstance(v, (dict, list)):
            continue
        lines.append(f"  {k}: {v}")

    # ── Audit findings (if any) ───────────────────────────────────────────────
    audit = payload.get("audit_report") or {}
    findings = audit.get("findings") or []
    high = [f for f in findings if f.get("severity") in {"critical", "high"}]
    if high:
        lines.append("")
        lines.append(f"Audit — {len(high)} high/critical finding(s):")
        for f in high[:5]:
            lines.append(f"  [{f.get('severity','?').upper()}] {_short(f.get('summary',''), 100)}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Headless eval: submit memo to CredenceAnalytics backend and print clean text output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(__doc__ or ""),
    )
    parser.add_argument("--ticker", nargs="+", default=[], help="Ticker(s) to verify against")
    parser.add_argument("--date", "--as-of-date", dest="as_of_date", default=None, help="As-of date (YYYY-MM-DD)")
    parser.add_argument("--memo", default=None, help="Inline memo text")
    parser.add_argument("--file", "-f", default=None, help="Path to memo text file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show LLM summaries and canonical facts")
    parser.add_argument("--mode", default="agentic", choices=["agentic", "strict"], help="Pipeline mode")
    parser.add_argument("--profile", default="agent_core", help="Tool profile (agent_core, retrieval_deep, macro_data)")
    args = parser.parse_args()

    # ── Resolve memo text ─────────────────────────────────────────────────────
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            memo = fh.read()
    elif args.memo:
        memo = args.memo
    elif not sys.stdin.isatty():
        memo = sys.stdin.read()
    else:
        parser.error("Provide memo via --memo, --file, or stdin.")

    memo = memo.strip()
    if not memo:
        parser.error("Memo text is empty.")

    # ── Run backend ───────────────────────────────────────────────────────────
    config = ToolkitConfig.from_env()
    print(f"[eval] Running pipeline… (mode={args.mode}, profile={args.profile})", file=sys.stderr)

    try:
        payload = build_verification_report(
            memo=memo,
            tickers=args.ticker or [],
            config=config,
            as_of_date=args.as_of_date,
            mode=args.mode,
            tool_profile=args.profile,
        )
    except Exception as exc:
        print(f"[eval] ERROR: {exc}", file=sys.stderr)
        raise

    # ── Print clean output ────────────────────────────────────────────────────
    print(_format_report(payload, verbose=args.verbose))


if __name__ == "__main__":
    main()
