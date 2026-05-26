"""Batch runner for CLI-driven credibility checks."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import ToolkitConfig
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
            if mode == "strict":
                pack = toolkit.build_evidence_pack(
                    claim=claim,
                    ticker=ticker,
                    as_of_date=as_of_date,
                    max_sources=max_sources,
                    mode="strict",
                )
            else:
                pack = AgenticCredibilityRunner(toolkit).run(
                    claim=claim,
                    ticker=ticker,
                    as_of_date=as_of_date,
                    max_sources=max_sources,
                )
            results.append({"row": index, "result": pack.to_dict()})
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
    for item in results:
        verdict = str((item.get("result") or {}).get("verdict") or "unknown")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "total": total,
        "succeeded": len(results),
        "failed": len(errors),
        "verdict_counts": verdict_counts,
    }
