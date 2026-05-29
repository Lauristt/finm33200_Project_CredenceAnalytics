"""Run a self-audit loop over saved equity-news samples.

The script feeds each sample through the same report builder used by the local
web UI, stores the rendered Markdown/JSON output, and then audits the output for
common-sense failures that should not require a user screenshot to catch.

Usage:
    PYTHONPATH=src python3 evaluation/equity_ui_audit_loop.py
    PYTHONPATH=src python3 evaluation/equity_ui_audit_loop.py --limit 3
    PYTHONPATH=src python3 evaluation/equity_ui_audit_loop.py --use-llm
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from financial_credibility.audit_agent import audit_verification_chain, summarize_audit_report  # noqa: E402
from financial_credibility.config import ToolkitConfig  # noqa: E402
from financial_credibility.models import to_plain  # noqa: E402
from financial_credibility.reporting import build_verification_report  # noqa: E402
from financial_credibility.sources import assess_source  # noqa: E402


SAMPLES = ROOT / "evaluation" / "equity_news_ui_audit_samples.json"
OUT_DIR = ROOT / "evaluation" / "equity_ui_audit_outputs"
RESULTS_JSON = ROOT / "evaluation" / "equity_ui_audit_results.json"
REPORT_MD = ROOT / "evaluation" / "equity_ui_audit_report.md"

POSITIVE_VERDICTS = {"supported", "verified", "partially_supported", "partially_verified"}
NEGATIVE_VERDICTS = {"contradicted"}
NON_FACT_VERDICTS = {"not_applicable"}
INSUFFICIENT_VERDICTS = {"insufficient", "not_found", "weak"}

INTERNAL_PATTERNS = (
    "HTTP Error",
    "Bad Request",
    "openai fallback",
    "anthropic fallback",
    "llm_source_selection_fallback",
    "ticker_only_entity_resolution",
)

PRICE_MOVE_RE = re.compile(
    r"\b(rose|rises|rising|fell|falls|falling|gained|gains|lost|slipped|climbed|"
    r"jumped|rallied|dropped|declined|added|closed|traded|to close|for the week|for the year)\b|%",
    re.IGNORECASE,
)
PRICE_CONTEXT_RE = re.compile(
    r"\b(stock|stocks|share|shares|price|quote|market|index|indexes|indices|after-hours|"
    r"premarket|S&P\s*500|Nasdaq|Dow|Russell|NYSE)\b",
    re.IGNORECASE,
)
FINANCIAL_METRIC_CONTEXT_RE = re.compile(
    r"\b(revenue|sales|net income|earnings|eps|operating income|free cash flow|cash flow|"
    r"gross margin|operating margin|net interest income|segment sales|cloud revenue|markets revenue)\b",
    re.IGNORECASE,
)
FORECAST_OR_OPINION_RE = re.compile(
    r"\b(expects?|forecast|guidance|guided|outlook|will|could|should|may|might|"
    r"best|safest|bull case|bear case|wary|concern|investors weighed|because|driven by)\b",
    re.IGNORECASE,
)
NUMERIC_RE = re.compile(r"[$€£]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|billion|million|trillion|bn|m|b)?", re.IGNORECASE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=SAMPLES)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--results-json", type=Path, default=RESULTS_JSON)
    parser.add_argument("--report-md", type=Path, default=REPORT_MD)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--use-llm", action="store_true", help="Use configured LLM instead of deterministic heuristic judge.")
    parser.add_argument("--agent-max-steps", type=int, default=20)
    args = parser.parse_args()

    samples = json.loads(args.samples.read_text(encoding="utf-8"))
    if args.limit:
        samples = samples[: args.limit]
    cfg = ToolkitConfig.from_env()
    if not args.use_llm:
        cfg = replace(
            cfg,
            llm_provider="heuristic",
            openai_api_key=None,
            openai_model=None,
            anthropic_api_key=None,
            anthropic_model=None,
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, sample in enumerate(samples, 1):
        print(f"[{index:>2}/{len(samples)}] {sample['id']}")
        report = build_verification_report(
            memo=sample["memo"],
            tickers=[],
            config=cfg,
            as_of_date=sample.get("published_at"),
            mode="multi_tool",
            tool_profile="agent_core",
            agent_max_steps=args.agent_max_steps,
            audit=True,
            source_results=sample_source_results(sample),
        )
        write_sample_output(args.out_dir, sample["id"], report)
        built_in_audit = report.get("audit_report") or {}
        custom_findings = audit_web_output(sample, report)
        results.append(
            {
                "sample": sample,
                "summary": compact_report_summary(report),
                "built_in_audit_summary": summarize_audit_report(built_in_audit) if built_in_audit else {},
                "custom_findings": custom_findings,
                "report_paths": {
                    "json": relative_path(args.out_dir / f"{sample['id']}.json"),
                    "markdown": relative_path(args.out_dir / f"{sample['id']}.md"),
                },
            }
        )

    args.results_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.results_json.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    args.report_md.write_text(render_audit_report(results), encoding="utf-8")
    print(f"\nWrote {relative_path(args.results_json)}")
    print(f"Wrote {relative_path(args.report_md)}")


def write_sample_output(out_dir: Path, sample_id: str, report: dict[str, Any]) -> None:
    (out_dir / f"{sample_id}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / f"{sample_id}.md").write_text(report.get("report_markdown") or "", encoding="utf-8")


def sample_source_results(sample: dict[str, Any]) -> list[dict[str, Any]]:
    """Seed official sample source pages without replacing structured retrieval."""
    url = str(sample.get("url") or "")
    if not url:
        return []
    title = str(sample.get("title") or sample.get("source") or "")
    source = str(sample.get("source") or "")
    lower_context = f"{title} {source}".lower()
    assessment = assess_source(url, title)
    if not assessment.is_official_primary and "investor relations" not in lower_context:
        return []
    return [
        {
            "title": title or source or "Sample source",
            "url": url,
            "snippet": str(sample.get("memo") or ""),
            "published_at": sample.get("published_at"),
            "source": source or None,
            "raw": {"provider": "audit_sample_source", "seed_source": True},
        }
    ]


def relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def compact_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    runs = report.get("runs") or []
    claims = [result for run in runs for result in run.get("atomic_claims") or []]
    return {
        "entities": [run.get("ticker") for run in runs],
        "entity_count": len(runs),
        "claim_count": len(claims),
        "fact_checked_count": sum(1 for result in claims if result.get("verdict") not in NON_FACT_VERDICTS),
        "not_fact_checked_count": sum(1 for result in claims if result.get("verdict") in NON_FACT_VERDICTS),
        "human_review_count": sum(1 for result in claims if result.get("human_review_required")),
        "verdict_counts": dict(Counter(str(result.get("verdict")) for result in claims)),
        "agent_termination": (report.get("agent_trace") or {}).get("termination_reason"),
        "markdown_lines": len((report.get("report_markdown") or "").splitlines()),
    }


def audit_web_output(sample: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    markdown = report.get("report_markdown") or ""
    payload_text = json.dumps(report, ensure_ascii=False)
    for pattern in INTERNAL_PATTERNS:
        if pattern in markdown:
            findings.append(finding("critical", "ui_leak", f"Rendered report leaks internal diagnostic text: {pattern}.", sample["id"]))
        elif pattern in payload_text and pattern in {"HTTP Error", "Bad Request", "openai fallback", "anthropic fallback"}:
            findings.append(finding("major", "payload_leak", f"Payload still contains provider/debug text: {pattern}.", sample["id"]))

    agent_trace = report.get("agent_trace") or {}
    if agent_trace.get("termination_reason") == "max_steps":
        findings.append(
            finding(
                "major",
                "agent_loop",
                "Agent stopped because it hit max_steps before finishing the sample.",
                sample["id"],
                "Increase the default web run budget or make retrieval batch-aware for multi-entity equity stories.",
            )
        )

    built_in = audit_verification_chain(report_payload=report, agent_trace=agent_trace)
    for item in to_plain(built_in).get("findings", []):
        if item.get("severity") in {"critical", "major"}:
            findings.append(
                finding(
                    item.get("severity", "major"),
                    f"built_in:{item.get('category', 'audit')}",
                    item.get("summary", "Audit finding."),
                    item.get("affected") or sample["id"],
                    item.get("recommendation") or "",
                )
            )

    for run in report.get("runs") or []:
        evidence = run.get("evidence") or []
        evidence_by_url = {item.get("url"): item for item in evidence if item.get("url")}
        evidence_by_key: dict[str, dict[str, Any]] = {}
        for item in evidence:
            evidence_by_key.setdefault(_evidence_key(item), item)
        for result in run.get("atomic_claims") or []:
            claim = result.get("atomic_claim") or {}
            text = str(claim.get("text") or "")
            verdict = str(result.get("verdict") or "")
            claim_id = f"{run.get('ticker')}:{claim.get('claim_id')}"
            linked = linked_evidence(result, evidence_by_url, evidence_by_key)
            positive = verdict in POSITIVE_VERDICTS

            if positive and not linked and not result.get("canonical_fact_ids"):
                findings.append(
                    finding(
                        "critical",
                        "evidence",
                        "Positive verdict has no linked evidence or canonical fact.",
                        claim_id,
                        "Cap the verdict at insufficient evidence until a relevant source is attached.",
                    )
                )

            if is_price_claim(text):
                if positive and not any(is_price_evidence(item) for item in linked):
                    findings.append(
                        finding(
                            "major",
                            "source_mismatch",
                            "Price or return claim was not supported by a historical-price source.",
                            claim_id,
                            "Route equity price, index move, and YTD return claims to historical_prices before verdicting.",
                        )
                    )
                if verdict in INSUFFICIENT_VERDICTS and not linked:
                    findings.append(
                        finding(
                            "major",
                            "missing_retrieval",
                            "Obvious price or return claim ended with no evidence.",
                            claim_id,
                            "Try the historical_prices adapter with a claim-specific time window.",
                        )
                    )

            if any(is_sec_company_facts(item) for item in linked) and is_price_claim(text):
                findings.append(
                    finding(
                        "critical",
                        "source_mismatch",
                        "SEC Company Facts was linked to a price/return claim.",
                        claim_id,
                        "Use market-price evidence for price moves; reserve SEC Company Facts for reported financial metrics.",
                    )
                )

            if positive and has_number(text) and not result.get("numeric_derivation"):
                findings.append(
                    finding(
                        "major",
                        "numeric",
                        "Numeric claim received a positive verdict without a deterministic numeric derivation.",
                        claim_id,
                        "Require a replayable numeric check for numeric claims before returning support.",
                    )
                )

            if looks_non_fact_checkable(text) and verdict not in NON_FACT_VERDICTS and not concrete_metric_claim(text):
                findings.append(
                    finding(
                        "major",
                        "claim_filter",
                        "Opinion, forecast, or causal commentary reached fact-checking.",
                        claim_id,
                        "Skip subjective or forward-looking commentary unless it contains a concrete, verifiable metric.",
                    )
                )

    return dedupe_findings(findings)


def finding(severity: str, category: str, summary: str, affected: str, recommendation: str = "") -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "summary": summary,
        "affected": affected,
        "recommendation": recommendation,
    }


def dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in findings:
        key = (item.get("severity"), item.get("category"), item.get("summary"), item.get("affected"))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def linked_evidence(
    result: dict[str, Any],
    evidence_by_url: dict[str, dict[str, Any]],
    evidence_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    for url in result.get("evidence_urls") or []:
        if url in evidence_by_url:
            items.append(evidence_by_url[url])
    for key in result.get("evidence_keys") or []:
        if key in evidence_by_key:
            items.append(evidence_by_key[key])
    return list({id(item): item for item in items}.values())


def _evidence_key(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "")
    url = str(item.get("url") or "")
    published = str(item.get("published_at") or "")
    return "|".join([title, url, published])


def is_price_claim(text: str) -> bool:
    raw = text or ""
    if FINANCIAL_METRIC_CONTEXT_RE.search(raw) and not PRICE_CONTEXT_RE.search(raw):
        return False
    if not PRICE_MOVE_RE.search(raw):
        return False
    if PRICE_CONTEXT_RE.search(raw):
        return True
    return bool(re.search(r"\b(rose|fell|gained|lost|slipped|climbed|jumped|rallied|dropped|declined)\b", raw, re.I))


def has_number(text: str) -> bool:
    return bool(NUMERIC_RE.search(text or ""))


def looks_non_fact_checkable(text: str) -> bool:
    return bool(FORECAST_OR_OPINION_RE.search(text or ""))


def concrete_metric_claim(text: str) -> bool:
    lower = text.lower()
    metric_terms = [
        "revenue",
        "sales",
        "net income",
        "earnings",
        "eps",
        "operating income",
        "net interest income",
        "markets revenue",
        "points",
        "%",
    ]
    return has_number(text) and any(term in lower for term in metric_terms)


def is_price_evidence(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key) or "") for key in ["title", "url", "text", "domain"]).lower()
    return any(
        marker in text
        for marker in [
            "historical prices",
            "historical daily close",
            "historical_prices",
            "financialmodelingprep",
            "alpha vantage",
            "finnhub",
            "stooq",
            "tiingo",
            "marketstack",
            "chart",
        ]
    )


def is_sec_company_facts(item: dict[str, Any]) -> bool:
    text = f"{item.get('title', '')} {item.get('url', '')}".lower()
    return "sec company facts" in text or "companyfacts" in text


def render_audit_report(results: list[dict[str, Any]]) -> str:
    all_findings = [finding for row in results for finding in row["custom_findings"]]
    by_severity = Counter(item["severity"] for item in all_findings)
    by_category = Counter(item["category"] for item in all_findings)
    lines = [
        "# Equity UI Audit Loop",
        "",
        f"Samples: {len(results)}",
        f"Findings: {len(all_findings)}",
        "",
        "## Finding Summary",
        "",
    ]
    for severity in ["critical", "major", "minor", "info"]:
        if by_severity.get(severity):
            lines.append(f"- {severity}: {by_severity[severity]}")
    if not all_findings:
        lines.append("- No custom audit findings.")
    lines.extend(["", "## Categories", ""])
    for category, count in by_category.most_common():
        lines.append(f"- {category}: {count}")
    lines.extend(["", "## Per Sample", ""])
    for row in results:
        sample = row["sample"]
        summary = row["summary"]
        findings = row["custom_findings"]
        lines.append(f"### {sample['id']}")
        lines.append("")
        lines.append(f"- Source: [{sample['source']}]({sample['url']})")
        lines.append(
            f"- Entities: {', '.join(summary['entities']) or 'none'}; "
            f"claims: {summary['claim_count']}; review: {summary['human_review_count']}; "
            f"termination: {summary.get('agent_termination') or 'n/a'}"
        )
        lines.append(f"- Output: `{row['report_paths']['markdown']}`")
        if findings:
            for item in findings[:8]:
                recommendation = f" Recommendation: {item['recommendation']}" if item.get("recommendation") else ""
                lines.append(
                    f"- **{item['severity']} / {item['category']}**: {item['summary']} "
                    f"Affected: `{item['affected']}`.{recommendation}"
                )
            if len(findings) > 8:
                lines.append(f"- ... {len(findings) - 8} more finding(s) in JSON.")
        else:
            lines.append("- No custom findings.")
        lines.append("")
    lines.extend(["## Suggested Next Fixes", ""])
    lines.extend(suggest_next_fixes(all_findings))
    return "\n".join(lines)


def suggest_next_fixes(findings: list[dict[str, Any]]) -> list[str]:
    counts = Counter(item["category"] for item in findings)
    suggestions = []
    if counts.get("agent_loop"):
        suggestions.append("- Increase the web UI multi-tool step budget or make it dynamic by detected entity count.")
    if counts.get("source_mismatch") or counts.get("missing_retrieval"):
        suggestions.append("- Harden routing so equity price/index move claims always call `historical_prices` with the inferred time window.")
    if counts.get("numeric"):
        suggestions.append("- Add a numeric-verdict gate: positive numeric verdicts require a replayable derivation.")
    if counts.get("claim_filter"):
        suggestions.append("- Tighten claim filtering for opinion, forecast, and causal commentary.")
    if counts.get("ui_leak") or counts.get("payload_leak"):
        suggestions.append("- Keep provider/debug errors out of user-facing payloads and rendered Markdown.")
    if not suggestions:
        suggestions.append("- No high-priority automated fix was identified by this audit pass.")
    return suggestions


if __name__ == "__main__":
    main()
