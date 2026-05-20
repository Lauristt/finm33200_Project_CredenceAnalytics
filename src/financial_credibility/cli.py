"""Command-line wrapper around `FinancialCredibilityToolkit`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ToolkitConfig
from .modes.agentic import AgenticCredibilityRunner
from .toolkit import FinancialCredibilityToolkit


def main() -> None:
    """Parse CLI args, run strict or agentic mode, and print JSON output."""
    parser = argparse.ArgumentParser(description="Build a financial credibility evidence pack.")
    parser.add_argument("claim", help="Financial claim to assess.")
    parser.add_argument("--ticker", required=True, help="US equity ticker, e.g. AAPL.")
    parser.add_argument("--as-of-date", default=None, help="Assessment date, YYYY-MM-DD.")
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--mode", choices=["strict", "agentic"], default="agentic")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--prefetched-json", default=None, help="JSON file containing search results.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    prefetched = None
    if args.prefetched_json:
        prefetched = json.loads(Path(args.prefetched_json).read_text(encoding="utf-8"))

    toolkit = FinancialCredibilityToolkit(ToolkitConfig.from_env(args.env_file))
    if args.mode == "agentic":
        pack = AgenticCredibilityRunner(toolkit).run(
            claim=args.claim,
            ticker=args.ticker,
            as_of_date=args.as_of_date,
            max_sources=args.max_sources,
            prefetched_results=prefetched,
        )
    else:
        pack = toolkit.build_evidence_pack(
            claim=args.claim,
            ticker=args.ticker,
            as_of_date=args.as_of_date,
            max_sources=args.max_sources,
            prefetched_results=prefetched,
            mode="strict",
        )

    indent = 2 if args.pretty else None
    print(json.dumps(pack.to_dict(), ensure_ascii=False, indent=indent))
