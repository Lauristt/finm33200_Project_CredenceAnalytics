"""Detailed SEC Company Facts benchmark for the stock subset of claims_news.json.

This evaluation is deliberately narrow: it filters `asset_class == "stock"` and
retrieves evidence only from SEC EDGAR Company Facts (`data.sec.gov` XBRL JSON).
That makes the result useful for debugging the SEC path without accidentally
letting web search, vendor data, or unrelated sources rescue a verdict.

Usage:
    PYTHONPATH=src python3 evaluation/eval_sec_stock.py
    PYTHONPATH=src python3 evaluation/eval_sec_stock.py --limit 5
    PYTHONPATH=src python3 evaluation/eval_sec_stock.py --use-llm
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from financial_credibility import FinancialCredibilityToolkit  # noqa: E402
from financial_credibility.config import ToolkitConfig  # noqa: E402
from financial_credibility.data_sources import FreeDataSourceClient  # noqa: E402
from financial_credibility.models import SearchResult, VerificationVerdict  # noqa: E402


DATA = ROOT / "evaluation" / "claims_news.json"
DEFAULT_OUT_PREFIX = ROOT / "evaluation" / "sec_stock_eval"
DEFAULT_AS_OF_DATE = "2026-05-28"

TRUE_VERDICTS = {
    VerificationVerdict.SUPPORTED.value,
    VerificationVerdict.VERIFIED.value,
}
LENIENT_TRUE_VERDICTS = TRUE_VERDICTS | {
    VerificationVerdict.PARTIALLY_SUPPORTED.value,
    VerificationVerdict.PARTIALLY_VERIFIED.value,
}
FALSE_VERDICTS = {VerificationVerdict.CONTRADICTED.value}
UNCERTAIN_VERDICTS = {
    VerificationVerdict.INSUFFICIENT.value,
    VerificationVerdict.NOT_FOUND.value,
    VerificationVerdict.WEAK.value,
}
NA_VERDICTS = {VerificationVerdict.NOT_APPLICABLE.value}


class CachedSECClient(FreeDataSourceClient):
    """SEC client with request cache and light throttling for repeatable evals."""

    def __init__(self, config: ToolkitConfig, min_interval: float = 0.2):
        super().__init__(config)
        self._text_cache: dict[str, str] = {}
        self._last_request_at = 0.0
        self._min_interval = min_interval

    def _get_text(self, url: str, sec: bool = False) -> str:
        if url in self._text_cache:
            return self._text_cache[url]
        wait = self._min_interval - (time.time() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        text = super()._get_text(url, sec=sec)
        self._last_request_at = time.time()
        self._text_cache[url] = text
        return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA)
    parser.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured LLM judge. Default is deterministic heuristic judge.",
    )
    parser.add_argument(
        "--include-na",
        action="store_true",
        default=True,
        help="Keep label=na rows in the benchmark. Enabled by default.",
    )
    args = parser.parse_args()

    rows = load_stock_rows(args.input)
    if args.limit:
        rows = rows[: args.limit]

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
    tk = FinancialCredibilityToolkit(cfg)
    sec_client = CachedSECClient(cfg)

    print(
        f"SEC stock eval | rows={len(rows)} | as_of={args.as_of_date} | "
        f"judge={type(tk.judge).__name__}"
    )
    print(f"labels={dict(Counter(item.get('label') for item in rows))}\n")

    results: list[dict[str, Any]] = []
    for index, item in enumerate(rows, 1):
        result = evaluate_one(tk, sec_client, item, args.as_of_date)
        results.append(result)
        print(
            f"[{index:>2}/{len(rows)}] {item['id']:<5} {item['entity']:<5} "
            f"{item['label']:<5} -> strict={result['predicted_strict']:<7} "
            f"lenient={result['predicted_lenient']:<7} sec={result['sec_evidence_count']}"
        )

    write_outputs(results, args.out_prefix)
    print_report(results, args.out_prefix)


def load_stock_rows(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in rows if row.get("asset_class") == "stock"]


def evaluate_one(
    tk: FinancialCredibilityToolkit,
    sec_client: CachedSECClient,
    row: dict[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    statement = row["statement"]
    ticker = row["entity"]
    traces: list[dict[str, Any]] = []

    try:
        sec_results = sec_client.sec_company_facts(statement, ticker, as_of_date=as_of_date)
        pack = tk.build_evidence_pack(
            claim=statement,
            ticker=ticker,
            as_of_date=as_of_date,
            max_sources=4,
            prefetched_results=sec_results,
            mode="strict",
            trace_callback=traces.append,
        )
        pack_dict = pack.to_dict()
        atomic = pack_dict.get("atomic_claims") or []
        verdicts = [str(item.get("verdict", "")) for item in atomic if item.get("verdict")]
        fact_checkable_verdicts = [verdict for verdict in verdicts if verdict not in NA_VERDICTS]
        predicted_strict = predicted_label(fact_checkable_verdicts, verdicts, lenient=False)
        predicted_lenient = predicted_label(fact_checkable_verdicts, verdicts, lenient=True)
        strict_correct = predicted_strict == row["label"]
        lenient_correct = predicted_lenient == row["label"]
        evidence = pack_dict.get("evidence") or []
        canonical = pack_dict.get("canonical_facts") or []
        metadata = pack_dict.get("metadata") or {}
        review_reasons = sorted(
            {
                reason
                for item in atomic
                for reason in item.get("review_reasons", [])
                if isinstance(reason, str)
            }
        )
        issues = sorted(
            {
                issue
                for item in atomic
                for issue in item.get("issues", [])
                if isinstance(issue, str)
            }
        )
        source_selection = metadata.get("source_selection") or []
        selected_providers = metadata.get("selected_providers") or []
        sec_urls = [result.url for result in sec_results]
        used_sec_urls = [
            item.get("url", "")
            for item in evidence
            if "data.sec.gov/api/xbrl/companyfacts" in str(item.get("url", ""))
        ]
        return {
            **base_row(row),
            "status": "ok",
            "predicted_strict": predicted_strict,
            "predicted_lenient": predicted_lenient,
            "strict_correct": strict_correct,
            "lenient_correct": lenient_correct,
            "overall_verdict": enumish(pack_dict.get("verdict", "")),
            "credibility_label": enumish(pack_dict.get("credibility_label", "")),
            "argument_type": enumish(pack_dict.get("argument_type", "")),
            "atomic_claim_count": len(atomic),
            "atomic_verdicts": "|".join(verdicts),
            "fact_checkable_verdicts": "|".join(fact_checkable_verdicts),
            "sec_evidence_count": len(sec_results),
            "used_sec_evidence_count": len(used_sec_urls),
            "canonical_fact_count": len(canonical),
            "evidence_count": len(evidence),
            "human_review_required": any(bool(item.get("human_review_required")) for item in atomic),
            "review_reasons": "|".join(review_reasons),
            "issues": "|".join(clean_issue(issue) for issue in issues),
            "selected_providers": "|".join(str(item) for item in selected_providers),
            "source_selection_summary": summarize_source_selection(source_selection),
            "sec_urls": "|".join(sec_urls),
            "used_sec_urls": "|".join(used_sec_urls),
            "evidence_titles": "|".join(str(item.get("title", "")) for item in evidence),
            "canonical_fact_names": "|".join(
                sorted({str(item.get("fact_name", "")) for item in canonical if item.get("fact_name")})
            ),
            "numeric_derivations": summarize_derivations(atomic),
            "trace_summary": summarize_trace(traces),
            "error": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **base_row(row),
            "status": "error",
            "predicted_strict": "error",
            "predicted_lenient": "error",
            "strict_correct": False,
            "lenient_correct": False,
            "overall_verdict": "error",
            "credibility_label": "error",
            "argument_type": "",
            "atomic_claim_count": 0,
            "atomic_verdicts": "",
            "fact_checkable_verdicts": "",
            "sec_evidence_count": 0,
            "used_sec_evidence_count": 0,
            "canonical_fact_count": 0,
            "evidence_count": 0,
            "human_review_required": True,
            "review_reasons": "evaluation_error",
            "issues": "",
            "selected_providers": "",
            "source_selection_summary": "",
            "sec_urls": "",
            "used_sec_urls": "",
            "evidence_titles": "",
            "canonical_fact_names": "",
            "numeric_derivations": "",
            "trace_summary": "",
            "error": clean_issue(str(exc)),
        }


def predicted_label(
    fact_checkable_verdicts: list[str],
    all_verdicts: list[str],
    *,
    lenient: bool,
) -> str:
    if not all_verdicts:
        return "review"
    if not fact_checkable_verdicts and all(verdict in NA_VERDICTS for verdict in all_verdicts):
        return "na"
    if any(verdict in FALSE_VERDICTS for verdict in fact_checkable_verdicts):
        return "false"
    true_set = LENIENT_TRUE_VERDICTS if lenient else TRUE_VERDICTS
    if fact_checkable_verdicts and all(verdict in true_set for verdict in fact_checkable_verdicts):
        return "true"
    if any(verdict in UNCERTAIN_VERDICTS for verdict in fact_checkable_verdicts):
        return "review"
    return "review"


def base_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "statement": row.get("statement", ""),
        "source": row.get("source", ""),
        "asset_class": row.get("asset_class", ""),
        "entity": row.get("entity", ""),
        "claim_type": row.get("claim_type", ""),
        "label": row.get("label", ""),
        "perturbation": row.get("perturbation", ""),
    }


def enumish(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def clean_issue(issue: str) -> str:
    if "HTTP Error" in issue or "fallback:" in issue:
        return "judge_fallback_or_request_error"
    return issue.replace("\n", " ")[:240]


def summarize_source_selection(plan: list[dict[str, Any]]) -> str:
    bits = []
    for item in plan:
        claim_id = item.get("claim_id", "?")
        selected = item.get("selected_provider_names") or item.get("selected_sources") or []
        bits.append(f"{claim_id}:{','.join(str(src) for src in selected)}")
    return "|".join(bits)


def summarize_derivations(atomic: list[dict[str, Any]]) -> str:
    parts = []
    for item in atomic:
        derivation = item.get("numeric_derivation") or {}
        if not derivation:
            continue
        expression = derivation.get("expression", "")
        passed = derivation.get("passed")
        result = derivation.get("result")
        notes = "; ".join(str(note) for note in derivation.get("notes", [])[:2])
        parts.append(f"{item.get('atomic_claim', {}).get('claim_id', '?')}:{expression};passed={passed};result={result};{notes}")
    return "|".join(parts)


def summarize_trace(events: list[dict[str, Any]]) -> str:
    return "|".join(f"{event.get('step')}:{event.get('status')}" for event in events)


def write_outputs(results: list[dict[str, Any]], prefix: Path) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    columns = [
        "id",
        "entity",
        "claim_type",
        "label",
        "predicted_strict",
        "predicted_lenient",
        "strict_correct",
        "lenient_correct",
        "status",
        "sec_evidence_count",
        "used_sec_evidence_count",
        "canonical_fact_count",
        "atomic_verdicts",
        "human_review_required",
        "review_reasons",
        "selected_providers",
        "canonical_fact_names",
        "numeric_derivations",
        "statement",
        "source",
        "perturbation",
        "error",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow({column: row.get(column, "") for column in columns})

    md_path.write_text(render_markdown(results), encoding="utf-8")


def print_report(results: list[dict[str, Any]], prefix: Path) -> None:
    summary = summarize(results)
    print("\n" + "=" * 72)
    print("SEC STOCK BENCHMARK SUMMARY")
    print("=" * 72)
    for key in [
        "rows",
        "strict_accuracy",
        "lenient_accuracy",
        "sec_retrieval_rate",
        "sec_used_rate",
        "human_review_rate",
        "error_rate",
    ]:
        print(f"{key}: {summary[key]}")
    print("\nOutputs:")
    print(f"- {prefix.with_suffix('.json')}")
    print(f"- {prefix.with_suffix('.csv')}")
    print(f"- {prefix.with_suffix('.md')}")


def summarize(results: list[dict[str, Any]]) -> dict[str, str]:
    total = len(results)
    strict_ok = sum(1 for row in results if row.get("strict_correct"))
    lenient_ok = sum(1 for row in results if row.get("lenient_correct"))
    sec_retrieved = sum(1 for row in results if int(row.get("sec_evidence_count") or 0) > 0)
    sec_used = sum(1 for row in results if int(row.get("used_sec_evidence_count") or 0) > 0)
    review = sum(1 for row in results if row.get("human_review_required"))
    errors = sum(1 for row in results if row.get("status") == "error")
    return {
        "rows": str(total),
        "strict_accuracy": pct(strict_ok, total),
        "lenient_accuracy": pct(lenient_ok, total),
        "sec_retrieval_rate": pct(sec_retrieved, total),
        "sec_used_rate": pct(sec_used, total),
        "human_review_rate": pct(review, total),
        "error_rate": pct(errors, total),
    }


def pct(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)" if denominator else "n/a"


def render_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# SEC Stock Claim Benchmark",
        "",
        "Scope: `evaluation/claims_news.json` rows where `asset_class == \"stock\"`. Evidence retrieval is restricted to SEC EDGAR Company Facts JSON from `data.sec.gov/api/xbrl/companyfacts`.",
        "",
        "Method: each statement is run through the same decomposition and verification path, but candidate evidence is pre-fetched only from SEC Company Facts. `strict` counts only fully supported/verified verdicts as true; `lenient` also counts partial support as true.",
        "",
        "## Summary",
        "",
    ]
    summary = summarize(results)
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    lines.extend(["", "## Diagnostic Takeaways", ""])
    lines.extend(diagnostic_takeaways(results))
    lines.extend(["", "## Highest-Priority Fixes", ""])
    lines.extend(priority_fixes(results))
    lines.extend(["", "## Label Distribution", ""])
    for label, count in Counter(row.get("label") for row in results).most_common():
        lines.append(f"- {label}: {count}")
    lines.extend(["", "## Claim Type Distribution", ""])
    for claim_type, count in Counter(row.get("claim_type") for row in results).most_common():
        lines.append(f"- {claim_type}: {count}")
    lines.extend(["", "## Strict Confusion Matrix", ""])
    lines.extend(confusion_table(results, "predicted_strict"))
    lines.extend(["", "## Lenient Confusion Matrix", ""])
    lines.extend(confusion_table(results, "predicted_lenient"))
    lines.extend(["", "## Mismatches And Review Rows", ""])
    mismatches = [
        row
        for row in results
        if not row.get("strict_correct") or row.get("human_review_required") or row.get("status") == "error"
    ]
    if not mismatches:
        lines.append("No strict mismatches or review rows.")
    else:
        for row in mismatches:
            reason = row.get("review_reasons") or row.get("error") or "n/a"
            facts = row.get("canonical_fact_names") or "no canonical facts"
            lines.append(
                f"- `{row['id']}` `{row['entity']}` label={row['label']} "
                f"strict={row['predicted_strict']} lenient={row['predicted_lenient']} "
                f"sec={row['used_sec_evidence_count']}/{row['sec_evidence_count']} "
                f"facts={facts}; reason={reason}. Claim: {row['statement']}"
            )
    lines.extend(["", "## Per-Entity SEC Coverage", ""])
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_entity[row["entity"]].append(row)
    for entity in sorted(by_entity):
        group = by_entity[entity]
        strict_ok = sum(1 for row in group if row.get("strict_correct"))
        sec_used = sum(1 for row in group if int(row.get("used_sec_evidence_count") or 0) > 0)
        lines.append(f"- {entity}: strict {pct(strict_ok, len(group))}; SEC used {pct(sec_used, len(group))}")
    lines.append("")
    return "\n".join(lines)


def diagnostic_takeaways(results: list[dict[str, Any]]) -> list[str]:
    total = len(results)
    true_rows = [row for row in results if row["label"] == "true"]
    false_rows = [row for row in results if row["label"] == "false"]
    na_rows = [row for row in results if row["label"] == "na"]
    true_as_na = sum(1 for row in true_rows if row["predicted_strict"] == "na")
    false_as_true_lenient = sum(1 for row in false_rows if row["predicted_lenient"] == "true")
    false_as_review = sum(1 for row in false_rows if row["predicted_strict"] == "review")
    na_correct = sum(1 for row in na_rows if row["predicted_strict"] == "na")
    sec_retrieved = sum(1 for row in results if int(row.get("sec_evidence_count") or 0) > 0)
    sec_used = sum(1 for row in results if int(row.get("used_sec_evidence_count") or 0) > 0)
    no_facts = sum(1 for row in results if int(row.get("canonical_fact_count") or 0) == 0)
    review_reasons = Counter()
    for row in results:
        for reason in filter(None, str(row.get("review_reasons", "")).split("|")):
            review_reasons[reason] += 1
    common_reasons = ", ".join(f"{reason}={count}" for reason, count in review_reasons.most_common(4)) or "none"
    return [
        f"- SEC retrieval itself is mostly working: {pct(sec_retrieved, total)} rows got a Company Facts result, but only {pct(sec_used, total)} rows used that SEC evidence in verification.",
        f"- The strict verifier currently produces no true/false decisions for this subset: many true rows become `na` ({pct(true_as_na, len(true_rows))}) or `review`, and false rows mostly become `review` ({pct(false_as_review, len(false_rows))}).",
        f"- Lenient scoring is unsafe right now: {pct(false_as_true_lenient, len(false_rows))} false rows become `true` because partial lexical support is not capped by numeric exactness.",
        f"- Opinion/forecast filtering is partly working: {pct(na_correct, len(na_rows))} `na` rows were correctly skipped under strict scoring.",
        f"- Canonical fact extraction is a bottleneck: {pct(no_facts, total)} rows ended with zero canonical SEC facts after retrieval.",
        f"- Top review reasons: {common_reasons}.",
    ]


def priority_fixes(results: list[dict[str, Any]]) -> list[str]:
    del results  # current recommendations are derived from the recurring failure modes above.
    return [
        "- Split mixed claims such as `reported revenue X, beating estimates Y`: SEC can verify the reported company metric, while analyst estimate comparisons need a separate estimates/news source or should be marked human review.",
        "- Strengthen SEC concept mapping for `adjusted EPS`, segment revenue, geography/product revenue, cloud/AWS/data-center revenue, and bank net-interest-income concepts.",
        "- Require numeric derivation for numeric SEC claims before returning supported/partially supported; otherwise cap the verdict at review/insufficient.",
        "- Keep forecast/opinion/causal explanation claims out of fact-check unless the sentence contains a concrete, SEC-verifiable metric.",
        "- Treat `used SEC evidence` separately from `retrieved SEC evidence`; retrieval alone should not count as coverage.",
    ]


def confusion_table(results: list[dict[str, Any]], prediction_field: str) -> list[str]:
    labels = ["true", "false", "na", "review", "error"]
    matrix: dict[str, Counter] = defaultdict(Counter)
    for row in results:
        matrix[row.get("label", "")][row.get(prediction_field, "")] += 1
    lines = ["| Expected | true | false | na | review | error |", "|---|---:|---:|---:|---:|---:|"]
    for expected in ["true", "false", "na"]:
        counts = matrix[expected]
        lines.append(
            "| "
            + expected
            + " | "
            + " | ".join(str(counts.get(label, 0)) for label in labels)
            + " |"
        )
    return lines


if __name__ == "__main__":
    main()
