"""Batch runner for CLI-driven credibility checks."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import ToolkitConfig
from .demo_presets import load_demo_preset
from .errors import UserFacingError
from .modes.agentic import AgenticCredibilityRunner
from .toolkit import FinancialCredibilityToolkit


REQUIRED_COLUMNS = {"claim", "ticker"}


def run_batch(
    input_path: str | Path,
    config: ToolkitConfig,
    default_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run multiple claim/ticker checks from a CSV file."""
    options = dict(default_options or {})
    rows = _read_csv_rows(input_path)
    toolkit = FinancialCredibilityToolkit(config)
    results = []
    errors = []
    default_prefetched = load_demo_preset(options.get("demo_preset"))

    for index, row in enumerate(rows, start=1):
        claim = str(row.get("claim") or "").strip()
        ticker = str(row.get("ticker") or "").strip().upper()
        if not claim or not ticker:
            errors.append({"row": index, "error": "missing claim or ticker"})
            continue
        try:
            mode = str(row.get("mode") or options.get("mode") or "agentic")
            max_sources = int(row.get("max_sources") or options.get("max_sources") or 8)
            as_of_date = row.get("as_of_date") or options.get("as_of_date")
            prefetched_results = default_prefetched
            if mode == "strict":
                pack = toolkit.build_evidence_pack(
                    claim=claim,
                    ticker=ticker,
                    as_of_date=as_of_date,
                    max_sources=max_sources,
                    prefetched_results=prefetched_results,
                    mode="strict",
                )
            else:
                pack = AgenticCredibilityRunner(toolkit).run(
                    claim=claim,
                    ticker=ticker,
                    as_of_date=as_of_date,
                    max_sources=max_sources,
                    prefetched_results=prefetched_results,
                )
            payload = pack.to_dict()
            if options.get("demo_preset"):
                payload["demo_mode"] = True
                payload["demo_preset"] = str(options["demo_preset"])
                payload["evidence_mode"] = "prefetched"
            results.append({"row": index, "result": payload})
        except Exception as exc:
            errors.append({"row": index, "ticker": ticker, "error": str(exc)})

    return {"summary": _summary(results, errors, len(rows)), "results": results, "errors": errors}


def _read_csv_rows(input_path: str | Path) -> list[dict[str, str]]:
    path = Path(input_path)
    if not path.exists():
        raise UserFacingError(
            "batch_input_not_found",
            f"Batch input file was not found: {path}",
            "Provide a CSV file with columns: claim,ticker,as_of_date,max_sources,mode.",
        )
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise UserFacingError(
                "batch_input_missing_columns",
                f"Batch input is missing required column(s): {', '.join(sorted(missing))}",
                "Use a CSV file with at least claim and ticker columns.",
            )
        return [dict(row) for row in reader]


def _summary(results: list[dict[str, Any]], errors: list[dict[str, Any]], total: int) -> dict[str, Any]:
    verdict_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    numeric_check_counts: dict[str, int] = {}
    source_check_counts: dict[str, int] = {}
    review_reason_counts: dict[str, int] = {}
    failure_mode_counts: dict[str, int] = {}
    credibility_scores: list[float] = []
    final_confidences: list[float] = []
    human_review_count = 0
    official_source_count = 0
    weak_source_count = 0

    for item in results:
        result = item.get("result") or {}
        verdict = str(result.get("verdict") or "unknown")
        _increment(verdict_counts, verdict)
        label = _overall_label(result)
        if label:
            _increment(label_counts, label)
        numeric_verdict = _check_verdict(result, "numeric_check")
        if numeric_verdict:
            _increment(numeric_check_counts, numeric_verdict)
        source_verdict = _check_verdict(result, "source_check")
        if source_verdict:
            _increment(source_check_counts, source_verdict)
            if source_verdict == "weak":
                weak_source_count += 1
        credibility = _float_or_none(result.get("credibility_score"))
        if credibility is not None:
            credibility_scores.append(credibility)
        final_confidence = _float_or_none((result.get("overall_conclusion") or {}).get("final_confidence"))
        if final_confidence is not None:
            final_confidences.append(final_confidence)
        evidence = result.get("evidence") or []
        if any((item or {}).get("is_official_primary") for item in evidence):
            official_source_count += 1
        row_review = False
        for atomic in result.get("atomic_claims") or []:
            if (atomic or {}).get("human_review_required"):
                row_review = True
            for reason in (atomic or {}).get("review_reasons") or []:
                _increment(review_reason_counts, str(reason))
        if row_review:
            human_review_count += 1
        for mode in _failure_modes(result):
            _increment(failure_mode_counts, mode)

    return {
        "total": total,
        "succeeded": len(results),
        "failed": len(errors),
        "verdict_counts": verdict_counts,
        "overall_label_counts": label_counts,
        "numeric_check_counts": numeric_check_counts,
        "source_check_counts": source_check_counts,
        "human_review_count": human_review_count,
        "review_reason_counts": review_reason_counts,
        "average_credibility_score": _average(credibility_scores),
        "average_final_confidence": _average(final_confidences),
        "official_source_count": official_source_count,
        "weak_source_count": weak_source_count,
        "diagnostics": {
            "common_failure_modes": sorted(failure_mode_counts, key=lambda key: (-failure_mode_counts[key], key)),
            "failure_mode_counts": failure_mode_counts,
        },
    }


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _check_verdict(result: dict[str, Any], key: str) -> str | None:
    check = result.get(key) or {}
    verdict = check.get("verdict")
    return str(verdict) if verdict else None


def _overall_label(result: dict[str, Any]) -> str | None:
    conclusion = result.get("overall_conclusion") or {}
    label = conclusion.get("overall_label") or result.get("credibility_label")
    return str(label) if label else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _failure_modes(result: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    numeric = _check_verdict(result, "numeric_check")
    source = _check_verdict(result, "source_check")
    if numeric in {"not_found", "insufficient"}:
        modes.append(f"numeric_{numeric}")
    if source == "weak":
        modes.append("weak_sources")
    if not (result.get("evidence") or []):
        modes.append("no_evidence")
    if any((atomic or {}).get("human_review_required") for atomic in result.get("atomic_claims") or []):
        modes.append("human_review_required")
    for atomic in result.get("atomic_claims") or []:
        for reason in (atomic or {}).get("review_reasons") or []:
            if "period" in str(reason) or "unit" in str(reason):
                modes.append("ambiguous_unit_or_period")
                break
    return sorted(set(modes))
