"""Command-line wrapper around `FinancialCredibilityToolkit`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch import run_batch
from .config import ToolkitConfig
from .demo_presets import available_demo_presets, load_demo_preset, normalize_demo_preset
from .errors import error_payload
from .modes.agentic import AgenticCredibilityRunner
from .models import to_plain
from .multi_tool_agent import MultiToolAgentRunner
from .tool_profiles import tool_profile_names
from .toolkit import FinancialCredibilityToolkit


def main() -> None:
    """Parse CLI args, run strict, agentic, or multi-tool mode, and print JSON output."""
    parser = argparse.ArgumentParser(description="Build a financial credibility evidence pack.")
    parser.add_argument("claim", nargs="?", help="Financial claim to assess.")
    parser.add_argument("--ticker", help="US equity ticker, e.g. AAPL.")
    parser.add_argument("--as-of-date", default=None, help="Assessment date, YYYY-MM-DD.")
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--mode", choices=["strict", "agentic", "multi-tool", "multi_tool"], default="agentic")
    parser.add_argument("--tool-profile", choices=tool_profile_names(), default="agent_core")
    parser.add_argument("--agent-max-steps", type=int, default=12)
    parser.add_argument("--audit", dest="audit", action="store_true", default=True, help="Attach an audit report in multi-tool mode.")
    parser.add_argument("--no-audit", dest="audit", action="store_false", help="Disable the multi-tool audit report.")
    parser.add_argument("--agent-trace-out", default=None, help="Write multi-tool agent trace JSON to this path.")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--prefetched-json", default=None, help="JSON file containing search results.")
    parser.add_argument("--demo-preset", choices=available_demo_presets(), default=None, help="Use a deterministic prefetched evidence preset.")
    parser.add_argument("--auto-report", action="store_true", help="Run memo-level report flow with automatic entity extraction.")
    parser.add_argument("--audit-out", default=None, help="Write audit trace JSON to this path.")
    parser.add_argument("--batch-input", default=None, help="CSV file with claim,ticker rows for batch verification.")
    parser.add_argument("--batch-output", default=None, help="Write batch JSON output to this path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    indent = 2 if args.pretty else None
    config = ToolkitConfig.from_env(args.env_file)

    try:
        if args.batch_input:
            result = run_batch(
                args.batch_input,
                config,
                {
                    "as_of_date": args.as_of_date,
                    "max_sources": args.max_sources,
                    "mode": args.mode,
                    "demo_preset": args.demo_preset,
                },
            )
            if args.batch_output:
                _write_json(args.batch_output, result, indent)
            print(json.dumps(result, ensure_ascii=False, indent=indent))
            return

        if not args.claim:
            parser.error("claim is required unless --batch-input is provided")
        if not args.ticker and args.mode not in {"multi-tool", "multi_tool"}:
            parser.error("--ticker is required unless --batch-input or --mode multi-tool is provided")

        prefetched = _prefetched_results(args.prefetched_json, args.demo_preset)
        demo_preset = normalize_demo_preset(args.demo_preset)

        if args.auto_report:
            report = build_verification_report(
                memo=args.claim,
                tickers=[args.ticker] if args.ticker else [],
                config=config,
                as_of_date=args.as_of_date,
                max_sources=args.max_sources,
                mode=args.mode,
                prefetched_results=prefetched,
            )
            _mark_demo_payload(report, demo_preset)
            print(json.dumps(report, ensure_ascii=False, indent=indent))
            return

        if not args.ticker:
            parser.error(
                "claim and --ticker are required for single-claim CLI mode; "
                "use --auto-report to run memo-level entity extraction, or --batch-input for CSV batch mode"
            )

        if args.mode in {"multi-tool", "multi_tool"}:
            result = MultiToolAgentRunner(config).run(
                memo=args.claim,
                tickers=[args.ticker] if args.ticker else [],
                as_of_date=args.as_of_date,
                max_steps=args.agent_max_steps,
                tool_profile=args.tool_profile,
                audit=args.audit,
                prefetched_results=prefetched,
            )
            if args.agent_trace_out:
                _write_json(args.agent_trace_out, result.get("agent_trace", {}), indent)
            if args.audit_out:
                _write_json(args.audit_out, result.get("audit_report", {}), indent)
            print(json.dumps(result, ensure_ascii=False, indent=indent))
            return

        toolkit = FinancialCredibilityToolkit(config)
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

        payload = pack.to_dict()
        _mark_demo_payload(payload, demo_preset)
        if args.audit_out:
            _write_json(args.audit_out, to_plain(pack.audit_trace), indent)
        print(json.dumps(payload, ensure_ascii=False, indent=indent))
    except Exception as exc:
        print(json.dumps(error_payload(exc), ensure_ascii=False, indent=indent))
        raise SystemExit(1) from exc


def _write_json(path: str, payload, indent: int | None) -> None:
    target = Path(path)
    if target.parent and not target.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {target.parent}")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")


def _prefetched_results(path: str | None, demo_preset: str | None) -> list[dict] | None:
    if path and demo_preset:
        raise ValueError("--prefetched-json and --demo-preset cannot be used together")
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return load_demo_preset(demo_preset)


def _mark_demo_payload(payload: dict, demo_preset: str | None) -> None:
    if not demo_preset:
        return
    payload["demo_mode"] = True
    payload["demo_preset"] = demo_preset
    payload["evidence_mode"] = "prefetched"
    if isinstance(payload.get("input"), dict):
        payload["input"]["demo_mode"] = True
        payload["input"]["demo_preset"] = demo_preset
        payload["input"]["evidence_mode"] = "prefetched"
