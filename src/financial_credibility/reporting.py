"""Report payload and Markdown rendering for memo-level verification."""

from __future__ import annotations

from statistics import mean
from typing import Any, Callable

from .config import ToolkitConfig
from .claims import decompose_claims
from .entity_extraction import extract_entities_from_memo, is_contextual_non_ticker_token
from .errors import UserFacingError
from .explanations import build_claim_explanation, explain_review_reasons
from .models import EvidencePack
from .modes.agentic import AgenticCredibilityRunner
from .price_history import PRICE_HISTORY_ASSET_CLASSES
from .preprocessing import preprocess_statement
from .time_context import infer_time_context
from .toolkit import FinancialCredibilityToolkit


_NON_TICKER_TOKENS = {
    "THE",
    "HOW",
    "US",
    "USA",
    "AM",
    "PM",
}

_PRICE_VERIFIABLE_REPORT_ASSET_CLASSES = {
    "equity_index",
    "equity_index_future",
    "fund_etf",
    "volatility_index",
} & PRICE_HISTORY_ASSET_CLASSES


def build_verification_report(
    memo: str,
    tickers: list[str],
    config: ToolkitConfig | None = None,
    as_of_date: str | None = None,
    max_sources: int = 8,
    mode: str = "agentic",
    prefetched_results: list[dict[str, Any]] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    tool_profile: str = "agent_core",
    agent_max_steps: int = 12,
    audit: bool = True,
) -> dict[str, Any]:
    """Run the verifier for each entity hint and return a report payload."""
    cfg = config or ToolkitConfig.from_env()
    if _is_multi_tool_mode(mode):
        from .multi_tool_agent import MultiToolAgentRunner

        return MultiToolAgentRunner(cfg).run(
            memo=memo,
            tickers=tickers,
            as_of_date=as_of_date,
            max_steps=agent_max_steps,
            tool_profile=tool_profile,
            audit=audit,
            prefetched_results=prefetched_results,
            progress_callback=progress_callback,
        )
    original_memo = memo
    preprocessed = preprocess_statement(memo)
    memo = preprocessed.clean_text
    _emit_progress(
        progress_callback,
        "preprocess_statement",
        "ok",
        "Removed copied-page boilerplate before verification." if preprocessed.changed else "Input did not require preprocessing.",
        outputs=preprocessed.to_dict(),
    )
    report_time_context = infer_time_context(memo, as_of_date)
    effective_as_of_date = report_time_context.effective_as_of_date or as_of_date
    _emit_progress(
        progress_callback,
        "infer_time_context",
        "ok" if effective_as_of_date else "empty",
        "Resolved the retrieval time context from the full statement.",
        outputs=report_time_context.to_dict(),
    )
    manual_tickers = _clean_tickers(tickers)
    _emit_progress(
        progress_callback,
        "extract_entities",
        "running",
        "Extracting financial entities and asset classes from the statement.",
    )
    entity_extraction = _manual_entity_extraction(manual_tickers) if manual_tickers else extract_entities_from_memo(memo, cfg)
    clean_tickers = manual_tickers or _verification_targets(entity_extraction) or infer_tickers(memo)
    _emit_progress(
        progress_callback,
        "extract_entities",
        "ok" if clean_tickers else "empty",
        f"Extracted {len(entity_extraction.get('entities', []))} financial entity hint(s).",
        outputs={
            "method": entity_extraction.get("method"),
            "tickers": clean_tickers,
            "asset_classes": entity_extraction.get("asset_classes", []),
            "unresolved_entities": entity_extraction.get("unresolved_entities", []),
        },
    )
    if not clean_tickers:
        if not entity_extraction.get("entities"):
            raise UserFacingError(
                "no_financial_entity_detected",
                "Could not extract a verifiable financial entity from the memo.",
                "Add a public-company ticker such as AAPL, or mention a supported financial asset more explicitly.",
            )
        payload = {
            "input": {
                "memo": memo,
                "original_memo": original_memo,
                "preprocessing": preprocessed.to_dict(),
                "tickers": [],
                "entity_extraction": entity_extraction,
                "as_of_date": effective_as_of_date,
                "requested_as_of_date": as_of_date,
                "time_context": report_time_context.to_dict(),
                "mode": mode,
                "max_sources": max_sources,
            },
            "summary": _summary([], [], entity_extraction),
            "runs": [],
            "errors": [],
        }
        _enhance_payload(payload)
        payload["report_markdown"] = render_markdown_report(payload)
        _emit_progress(
            progress_callback,
            "compose_report",
            "ok",
            "Composed detected asset-class report; no public-company verification target was available.",
            outputs={"entity_count": 0, "asset_classes": entity_extraction.get("asset_classes", [])},
        )
        return payload

    toolkit = FinancialCredibilityToolkit(cfg)
    runs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for ticker in clean_tickers:
        _emit_progress(
            progress_callback,
            "run_entity",
            "running",
            f"Starting verification for {ticker}.",
            outputs={"ticker": ticker},
        )
        try:
            scoped_memo = _memo_for_ticker(memo, ticker, entity_extraction) if len(clean_tickers) > 1 else memo
            pack = _run_pack(
                toolkit=toolkit,
                memo=scoped_memo,
                ticker=ticker,
                as_of_date=effective_as_of_date,
                max_sources=max_sources,
                mode=mode,
                prefetched_results=prefetched_results,
                trace_callback=_scoped_progress(progress_callback, ticker),
            )
            runs.append(pack.to_dict())
            _emit_progress(
                progress_callback,
                "run_entity",
                "ok",
                f"Finished verification for {ticker}.",
                outputs={"ticker": ticker, "atomic_claim_count": len(pack.atomic_claims)},
            )
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
            _emit_progress(
                progress_callback,
                "run_entity",
                "error",
                f"Verification failed for {ticker}: {exc}",
                outputs={"ticker": ticker},
            )

    payload = {
        "input": {
            "memo": memo,
            "original_memo": original_memo,
            "preprocessing": preprocessed.to_dict(),
            "tickers": clean_tickers,
            "entity_extraction": entity_extraction,
            "as_of_date": effective_as_of_date,
            "requested_as_of_date": as_of_date,
            "time_context": report_time_context.to_dict(),
            "mode": mode,
            "max_sources": max_sources,
        },
        "summary": _summary(runs, errors, entity_extraction),
        "runs": runs,
        "errors": errors,
    }
    _enhance_payload(payload)
    payload["report_markdown"] = render_markdown_report(payload)
    _emit_progress(
        progress_callback,
        "compose_report",
        "ok",
        "Composed final verification report.",
        outputs={"entity_count": len(runs), "error_count": len(errors)},
    )
    return payload


def render_markdown_report(payload: dict[str, Any]) -> str:
    """Render a compact, portable Markdown report from a report payload."""
    summary = payload.get("summary", {})
    lines = [
        "# Credence Verification Report",
        "",
        "## Summary",
        "",
        f"- Entities checked: {summary.get('entity_count', 0)}",
        f"- Fact-checked claims: {summary.get('atomic_claim_count', 0)}",
        f"- Skipped opinion/forecast claims: {summary.get('skipped_claim_count', 0)}",
        f"- Human review required: {summary.get('human_review_count', 0)}",
        f"- Average confidence: {_fmt_conf(summary.get('average_confidence'))}",
        "",
    ]
    coverage = payload.get("coverage_summary") or {}
    coverage_rows = coverage.get("entities") or []
    if coverage_rows:
        lines.extend(
            [
                "## Verification Coverage",
                "",
                "| Entity | Asset Class | Status | Reason |",
                "|---|---|---|---|",
            ]
        )
        for item in coverage_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(item.get("label", "")),
                        _md_cell(_asset_class_label(str(item.get("asset_class", "")))),
                        _md_cell(item.get("verification_status", "")),
                        _md_cell(item.get("reason", "")),
                    ]
                )
                + " |"
            )
        if coverage.get("notes"):
            lines.append("")
            for note in coverage.get("notes", []):
                lines.append(f"- {note}")
        lines.append("")
    extraction = (payload.get("input") or {}).get("entity_extraction") or {}
    if extraction:
        groups = extraction.get("asset_groups") or _group_entities_by_asset_class(extraction.get("entities", []))
        if groups:
            lines.extend(["## Detected Asset Classes", ""])
            for asset_class, entities in groups.items():
                labels = [_entity_label(entity) for entity in entities if _entity_label(entity)]
                lines.append(f"- {_asset_class_label(asset_class)}: {', '.join(labels) or 'n/a'}")
            lines.append("")
    if payload.get("errors"):
        lines.extend(["## Errors", ""])
        for error in payload["errors"]:
            lines.append(f"- {error.get('ticker')}: {error.get('error')}")
        lines.append("")
    agent_trace = payload.get("agent_trace") or {}
    if agent_trace.get("tool_calls"):
        lines.extend(
            [
                "## Multi-Tool Agent Trace",
                "",
                f"- Provider: {agent_trace.get('provider', 'n/a')}",
                f"- Tool profile: {agent_trace.get('tool_profile', 'n/a')}",
                f"- Termination: {agent_trace.get('termination_reason', 'n/a')}",
                "",
                "| Turn | Tool | Status | Duration ms | Error |",
                "|---:|---|---|---:|---|",
            ]
        )
        for call in agent_trace.get("tool_calls") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(call.get("turn_index", "")),
                        _md_cell(call.get("tool_name", "")),
                        _md_cell(call.get("status", "")),
                        _md_cell(call.get("duration_ms", "")),
                        _md_cell(call.get("error") or ""),
                    ]
                )
                + " |"
            )
        lines.append("")
    audit_report = payload.get("audit_report") or {}
    if audit_report:
        lines.extend(
            [
                "## Audit Report",
                "",
                f"- Verdict: {audit_report.get('verdict', 'n/a')}",
                f"- Score: {_fmt_conf(audit_report.get('score'))}",
                f"- Summary: {audit_report.get('summary', '')}",
                "",
            ]
        )
        findings = audit_report.get("findings") or []
        if findings:
            lines.extend(
                [
                    "| Severity | Category | Finding | Affected | Recommendation |",
                    "|---|---|---|---|---|",
                ]
            )
            for finding in findings:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md_cell(finding.get("severity", "")),
                            _md_cell(finding.get("category", "")),
                            _md_cell(finding.get("summary", "")),
                            _md_cell(finding.get("affected", "")),
                            _md_cell(finding.get("recommendation", "")),
                        ]
                    )
                    + " |"
                )
            lines.append("")

    for run in payload.get("runs", []):
        ticker = run.get("ticker", "")
        lines.extend(
            [
                f"## {ticker}",
                "",
                f"- Overall: {run.get('overall_conclusion', {}).get('overall_label', 'n/a')}",
                "",
            ]
        )
        selections = (run.get("metadata") or {}).get("source_selection") or []
        if selections:
            lines.extend(["### Selected Sources", ""])
            for selection in selections:
                sources = ", ".join(selection.get("selected_sources") or [])
                rationale = selection.get("rationale", "")
                lines.append(f"- `{selection.get('claim_id') or 'claim'}`: {sources}. {rationale}")
            lines.append("")
        debug_rows = run.get("source_selection_debug") or []
        if debug_rows:
            lines.extend(
                [
                    "### Source Selection Explanation",
                    "",
                    "| Claim | Selected Sources | Policy Result | Rationale |",
                    "|---|---|---|---|",
                ]
            )
            for item in debug_rows:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md_cell(item.get("claim_id", "")),
                            _md_cell(", ".join(item.get("selected_sources") or []) or "n/a"),
                            _md_cell(item.get("official_first_policy", "")),
                            _md_cell(item.get("rationale", "")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        trace = run.get("audit_trace") or {}
        if trace.get("events"):
            lines.extend(["### Agent Trace", ""])
            for event in trace.get("events", []):
                lines.append(
                    f"- `{event.get('step', 'step')}` [{event.get('status', 'n/a')}]: "
                    f"{event.get('summary', '')}"
                )
            lines.append("")
        checked_results = [result for result in run.get("atomic_claims", []) if not _is_skipped_result(result)]
        skipped_results = [result for result in run.get("atomic_claims", []) if _is_skipped_result(result)]
        if checked_results:
            lines.extend(
                [
                    "| Claim | Verdict | Confidence | Human Review | Evidence | Derivation |",
                    "|---|---|---:|---|---|---|",
                ]
            )
        for result in checked_results:
            claim = (result.get("atomic_claim") or {}).get("text", "")
            components = result.get("confidence_components") or {}
            confidence = _fmt_conf(components.get("final_confidence"))
            review = ", ".join(result.get("review_reasons") or []) or "No"
            evidence = ", ".join(result.get("evidence_keys") or result.get("evidence_urls") or []) or "n/a"
            derivation = _format_derivation(result.get("numeric_derivation"))
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(claim),
                        _md_cell(result.get("verdict", "")),
                        _md_cell(confidence),
                        _md_cell(review),
                        _md_cell(evidence),
                        _md_cell(derivation),
                    ]
                )
                + " |"
            )
        lines.append("")
        explanations = run.get("claim_explanations") or []
        if explanations:
            lines.extend(["### Claim Explanations", ""])
            for explanation in explanations:
                lines.extend(
                    [
                        f"#### {explanation.get('claim_id', 'claim')}",
                        "",
                        f"- Claim: {explanation.get('claim', '')}",
                        f"- Verdict: {explanation.get('verdict', 'n/a')}",
                        f"- Explanation: {explanation.get('summary', '')}",
                        f"- Numeric check: {explanation.get('numeric_summary', '')}",
                        f"- Source quality: {explanation.get('source_summary', '')}",
                    ]
                )
                caveats = explanation.get("caveats") or []
                if caveats:
                    lines.append(f"- Caveats: {'; '.join(caveats)}")
                lines.append("")
        review_explanations = _review_explanations_for_run(run)
        if review_explanations:
            lines.extend(["### Human Review Explanations", ""])
            for item in review_explanations:
                lines.append(
                    f"- `{item.get('code')}`: {item.get('description')} "
                    f"Recommended action: {item.get('recommended_action')}"
                )
            lines.append("")
        if skipped_results:
            lines.extend(["### Not Fact-Checked", ""])
            for result in skipped_results:
                claim = (result.get("atomic_claim") or {}).get("text", "")
                claim_type = (result.get("atomic_claim") or {}).get("argument_type", "n/a")
                lines.append(f"- `{claim_type}`: {claim}")
            lines.append("")
        lines.extend(["### Evidence", ""])
        for evidence in run.get("evidence", [])[:8]:
            lines.append(
                f"- [{evidence.get('source_tier')}] {evidence.get('title')} "
                f"({evidence.get('domain')}) - {evidence.get('url')}"
            )
        lines.append("")
        provenance = run.get("evidence_provenance") or []
        if provenance:
            lines.extend(
                [
                    "### Evidence Provenance",
                    "",
                    "| Source | Tier | Official | License | Date | Used By | URL |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for item in provenance:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md_cell(item.get("title", "")),
                            _md_cell(item.get("source_tier", "")),
                            _md_cell("Yes" if item.get("is_official_primary") else "No"),
                            _md_cell(item.get("license_tag", "")),
                            _md_cell(item.get("published_at") or "n/a"),
                            _md_cell(", ".join(item.get("used_by_claims") or []) or "n/a"),
                            _md_cell(item.get("url", "")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _enhance_payload(payload: dict[str, Any]) -> None:
    """Attach report-layer explainability structures in place."""
    extraction = (payload.get("input") or {}).get("entity_extraction") or {}
    payload["coverage_summary"] = _build_coverage_summary(payload.get("runs", []), extraction)
    for run in payload.get("runs", []):
        evidence_lookup = {item.get("url", ""): item for item in run.get("evidence", []) if item.get("url")}
        run["evidence_provenance"] = _build_evidence_provenance(run)
        run["claim_explanations"] = [
            build_claim_explanation(result, evidence_lookup)
            for result in run.get("atomic_claims", [])
            if not _is_skipped_result(result)
        ]
        run["source_selection_debug"] = _build_source_selection_debug(run)
        run["audit_export"] = _build_audit_export_summary(run)


def _build_coverage_summary(
    runs: list[dict[str, Any]],
    entity_extraction: dict[str, Any],
) -> dict[str, Any]:
    verified_tickers = {str(run.get("ticker", "")).upper() for run in runs if run.get("ticker")}
    rows = []
    for entity in entity_extraction.get("entities", []):
        ticker = str(entity.get("ticker") or "").upper()
        asset_class = str(entity.get("asset_class") or "other")
        label = _entity_label(entity)
        symbol = str(entity.get("symbol") or "").upper()
        verified_key = ticker or symbol
        if ticker and ticker in verified_tickers and asset_class == "single_name_equity":
            status = "fully_verified"
            reason = "Public-company verification path was run for this entity."
        elif (
            asset_class in _PRICE_VERIFIABLE_REPORT_ASSET_CLASSES
            and verified_key
            and verified_key in verified_tickers
        ):
            status = "fully_verified"
            reason = "Price/market-data verification path was run for this asset."
        elif asset_class == "single_name_equity" and ticker:
            status = "not_verified"
            reason = "The entity was detected but no successful verification run was produced."
        else:
            status = "detected_only"
            reason = f"No full claim-level verifier is currently implemented for {asset_class} in this report flow."
        rows.append(
            {
                "label": label,
                "name": entity.get("name"),
                "ticker": entity.get("ticker"),
                "symbol": entity.get("symbol"),
                "asset_class": asset_class,
                "verification_status": status,
                "reason": reason,
            }
        )
    notes = []
    if any(item["verification_status"] == "detected_only" for item in rows):
        notes.append("Detected-only assets are surfaced for scope transparency; they should not be read as fully verified claims.")
    return {
        "entities": rows,
        "fully_verified_entities": [item for item in rows if item["verification_status"] == "fully_verified"],
        "detected_only_entities": [item for item in rows if item["verification_status"] == "detected_only"],
        "unsupported_asset_classes": sorted(
            {item["asset_class"] for item in rows if item["verification_status"] == "detected_only"}
        ),
        "notes": notes,
    }


def _build_evidence_provenance(run: dict[str, Any]) -> list[dict[str, Any]]:
    used_by_url: dict[str, list[str]] = {}
    for result in run.get("atomic_claims", []):
        claim_id = (result.get("atomic_claim") or {}).get("claim_id", "claim")
        for url in result.get("evidence_urls") or []:
            used_by_url.setdefault(url, []).append(claim_id)
    provenance = []
    for item in run.get("evidence", []):
        url = item.get("url", "")
        provenance.append(
            {
                "title": item.get("title", ""),
                "domain": item.get("domain", ""),
                "source_tier": item.get("source_tier", ""),
                "is_official_primary": bool(item.get("is_official_primary")),
                "license_tag": item.get("license_tag", ""),
                "published_at": item.get("published_at"),
                "url": url,
                "used_by_claims": sorted(set(used_by_url.get(url, []))),
            }
        )
    return provenance


def _build_source_selection_debug(run: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    selections = (run.get("metadata") or {}).get("source_selection") or []
    for selection in selections:
        selected = selection.get("selected_sources") or []
        rows.append(
            {
                "claim_id": selection.get("claim_id") or "claim",
                "selected_sources": selected,
                "rationale": selection.get("rationale", ""),
                "method": selection.get("method", ""),
                "official_first_policy": "passed" if _has_official_source(selected) else "needs_review",
            }
        )
    return rows


def _build_audit_export_summary(run: dict[str, Any]) -> dict[str, Any]:
    trace = run.get("audit_trace") or {}
    events = trace.get("events") or []
    failed = [event for event in events if event.get("status") in {"error", "failed"}]
    return {
        "trace_id": trace.get("trace_id"),
        "event_count": len(events),
        "failed_steps": [event.get("step") for event in failed],
        "download_ready": bool(trace),
    }


def _review_explanations_for_run(run: dict[str, Any]) -> list[dict[str, str]]:
    codes = []
    for result in run.get("atomic_claims", []):
        codes.extend(result.get("review_reasons") or [])
    return explain_review_reasons(codes)


def _has_official_source(source_ids: list[str]) -> bool:
    official_markers = {
        "sec_company_facts",
        "sec_recent_filings",
        "treasury_fiscal_data",
        "fred",
        "gleif_entity",
    }
    return bool(set(source_ids) & official_markers)


def infer_tickers(text: str) -> list[str]:
    """Infer simple ticker hints from $AAPL, (AAPL), or standalone uppercase tokens."""
    import re

    candidates = re.findall(r"\$([A-Z]{1,5})\b|\(([A-Z]{1,5})\)|\b([A-Z]{2,5})\b", text)
    tickers = []
    stopwords = {
        "SEC", "CEO", "CFO", "EPS", "EBITDA", "GDP", "CPI", "USA", "USD", "GAAP", "MD",
        "SPX", "NDX", "DJIA", "RUT", "VIX", "ES", "NQ", "RTY", "CL", "GC", "SI", "HG", "NG",
        "DXY", "NFP", "SOFR", "DGS10", "DGS2", "BTC", "ETH", "SPY", "QQQ", "IWM", "HYG",
        "LQD", "TLT", "GLD", "USO", "WTI", "BRENT", "EUR", "JPY", "GBP", "CAD", "AUD",
        "CHF", "CNY", "CNH", "HY", "IG", "THE", "HOW", "US",
    }
    for groups in candidates:
        token = next((item for item in groups if item), "")
        if token and token not in stopwords and not is_contextual_non_ticker_token(token, text):
            tickers.append(token)
    return _clean_tickers(tickers)


def _manual_entity_extraction(tickers: list[str]) -> dict[str, Any]:
    return {
        "method": "manual_input",
        "entities": [
            {
                "name": ticker,
                "ticker": ticker,
                "symbol": ticker,
                "entity_type": "public_company",
                "asset_class": "single_name_equity",
                "confidence": 1.0,
                "source": "manual_input",
                "reason": "User supplied entity hint.",
            }
            for ticker in tickers
        ],
        "tickers": tickers,
        "asset_classes": ["single_name_equity"] if tickers else [],
        "asset_groups": {
            "single_name_equity": [
                {
                    "name": ticker,
                    "ticker": ticker,
                    "symbol": ticker,
                    "entity_type": "public_company",
                    "asset_class": "single_name_equity",
                    "confidence": 1.0,
                    "source": "manual_input",
                    "reason": "User supplied entity hint.",
                }
                for ticker in tickers
            ]
        }
        if tickers
        else {},
        "unresolved_entities": [],
        "non_equity_entities": [],
        "notes": [],
    }


def _verification_targets(entity_extraction: dict[str, Any]) -> list[str]:
    targets = []
    targets.extend(entity_extraction.get("tickers") or [])
    for entity in entity_extraction.get("entities", []):
        asset_class = str(entity.get("asset_class") or "")
        symbol = str(entity.get("symbol") or entity.get("ticker") or "").upper()
        if asset_class in _PRICE_VERIFIABLE_REPORT_ASSET_CLASSES and symbol:
            targets.append(symbol)
    return _clean_tickers(targets)


def _memo_for_ticker(memo: str, ticker: str, entity_extraction: dict[str, Any]) -> str:
    aliases = _aliases_for_ticker(ticker, entity_extraction)
    matched = [
        atom.text
        for atom in decompose_claims(memo)
        if _claim_mentions_alias(atom.text, aliases)
    ]
    return "; ".join(matched) if matched else memo


def _aliases_for_ticker(ticker: str, entity_extraction: dict[str, Any]) -> list[str]:
    aliases = [ticker]
    for entity in entity_extraction.get("entities", []):
        entity_ticker = str(entity.get("ticker") or "").upper()
        entity_symbol = str(entity.get("symbol") or "").upper()
        if ticker.upper() not in {entity_ticker, entity_symbol}:
            continue
        name = str(entity.get("name") or "").strip()
        symbol = str(entity.get("symbol") or "").strip()
        aliases.extend([symbol])
        aliases.extend(_name_aliases(name))
        aliases.extend(_market_symbol_aliases(symbol or ticker))
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _name_aliases(name: str) -> list[str]:
    if not name:
        return []
    cleaned = name.replace(",", " ")
    cleaned = _strip_company_suffixes(cleaned)
    aliases = [name, cleaned]
    first_word = cleaned.split()[0] if cleaned.split() else ""
    if len(first_word) > 4 and first_word.lower() not in {"bank", "company"}:
        aliases.append(first_word)
    if ".com" in cleaned.lower():
        aliases.append(cleaned.split(".com", 1)[0])
    return aliases


def _market_symbol_aliases(symbol: str) -> list[str]:
    return {
        "SPX": ["S&P 500", "S and P 500"],
        "NDQ": ["Nasdaq", "Nasdaq Composite"],
        "NDX": ["Nasdaq 100"],
        "DJIA": ["Dow", "Dow Jones", "Dow Jones Industrial Average"],
        "RUT": ["Russell", "Russell 2000"],
    }.get(str(symbol or "").upper(), [])


def _strip_company_suffixes(value: str) -> str:
    import re

    cleaned = re.sub(
        r"\b(inc|inc\.|corporation|corp|corp\.|company|co|co\.|ltd|ltd\.|plc|class [a-z])\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" .")


def _claim_mentions_alias(claim: str, aliases: list[str]) -> bool:
    import re

    for alias in aliases:
        if not alias:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"
        if re.search(pattern, claim, flags=re.IGNORECASE):
            return True
    return False


def _run_pack(
    toolkit: FinancialCredibilityToolkit,
    memo: str,
    ticker: str,
    as_of_date: str | None,
    max_sources: int,
    mode: str,
    prefetched_results: list[dict[str, Any]] | None,
    trace_callback: Callable[[dict[str, Any]], None] | None = None,
) -> EvidencePack:
    kwargs = {
        "claim": memo,
        "ticker": ticker,
        "as_of_date": as_of_date,
        "max_sources": max_sources,
        "prefetched_results": prefetched_results,
    }
    if mode == "strict":
        return toolkit.build_evidence_pack(**kwargs, mode="strict", trace_callback=trace_callback)
    return AgenticCredibilityRunner(toolkit).run(**kwargs, trace_callback=trace_callback)


def _is_multi_tool_mode(mode: str) -> bool:
    return str(mode or "").replace("-", "_").lower() == "multi_tool"


def _emit_progress(
    callback: Callable[[dict[str, Any]], None] | None,
    step: str,
    status: str,
    summary: str,
    outputs: dict[str, Any] | None = None,
) -> None:
    if not callback:
        return
    callback(
        {
            "step": step,
            "status": status,
            "summary": summary,
            "inputs": {},
            "outputs": outputs or {},
        }
    )


def _scoped_progress(
    callback: Callable[[dict[str, Any]], None] | None,
    ticker: str,
) -> Callable[[dict[str, Any]], None] | None:
    if not callback:
        return None

    def emit(event: dict[str, Any]) -> None:
        scoped = dict(event)
        outputs = dict(scoped.get("outputs") or {})
        outputs.setdefault("ticker", ticker)
        scoped["outputs"] = outputs
        scoped["entity"] = ticker
        callback(scoped)

    return emit


def _summary(
    runs: list[dict[str, Any]],
    errors: list[dict[str, str]],
    entity_extraction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    atomic_results = [
        result
        for run in runs
        for result in run.get("atomic_claims", [])
    ]
    checked_results = [result for result in atomic_results if not _is_skipped_result(result)]
    skipped_results = [result for result in atomic_results if _is_skipped_result(result)]
    confidences = [
        (result.get("confidence_components") or {}).get("final_confidence")
        for result in checked_results
        if (result.get("confidence_components") or {}).get("final_confidence") is not None
    ]
    entities = (entity_extraction or {}).get("entities", [])
    asset_classes = (entity_extraction or {}).get("asset_classes", [])
    return {
        "entity_count": len(runs),
        "detected_entity_count": len(entities),
        "asset_class_count": len(asset_classes),
        "asset_classes": asset_classes,
        "non_equity_entity_count": len((entity_extraction or {}).get("non_equity_entities", [])),
        "error_count": len(errors),
        "atomic_claim_count": len(checked_results),
        "skipped_claim_count": len(skipped_results),
        "total_claim_count": len(atomic_results),
        "human_review_count": sum(1 for result in checked_results if result.get("human_review_required")),
        "average_confidence": round(mean(confidences), 3) if confidences else None,
    }


def _is_skipped_result(result: dict[str, Any]) -> bool:
    if result.get("verdict") == "not_applicable":
        return True
    claim_type = (result.get("atomic_claim") or {}).get("argument_type")
    return claim_type in {"forecast", "opinion_analysis"}


def _clean_tickers(tickers: list[str]) -> list[str]:
    cleaned = []
    for ticker in tickers:
        for part in str(ticker).replace(";", ",").split(","):
            normalized = part.strip().upper().lstrip("$")
            if normalized and normalized not in _NON_TICKER_TOKENS:
                cleaned.append(normalized)
    return list(dict.fromkeys(cleaned))


def _format_derivation(derivation: dict[str, Any] | None) -> str:
    if not derivation:
        return "n/a"
    expression = derivation.get("expression") or "numeric check"
    result = derivation.get("result")
    passed = derivation.get("passed")
    if passed is None:
        return str(expression)
    return f"{expression}; result={result}; passed={passed}"


def _fmt_conf(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _entity_label(entity: dict[str, Any]) -> str:
    ticker = entity.get("ticker")
    symbol = entity.get("symbol")
    name = entity.get("name")
    if ticker and name and ticker != name:
        return f"{name} ({ticker})"
    if symbol and name and symbol != name:
        return f"{name} ({symbol})"
    return str(ticker or symbol or name or "")


def _group_entities_by_asset_class(entities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        asset_class = str(entity.get("asset_class") or "other")
        groups.setdefault(asset_class, []).append(entity)
    return groups


def _asset_class_label(asset_class: str) -> str:
    return {
        "single_name_equity": "Single-name equities",
        "equity_index": "Equity indexes",
        "equity_index_future": "Equity index futures",
        "fund_etf": "Funds and ETFs",
        "commodity": "Commodities",
        "commodity_future": "Commodity futures",
        "fx": "FX",
        "rates": "Rates",
        "credit": "Credit",
        "macro_indicator": "Macro indicators",
        "crypto": "Crypto",
        "fixed_income": "Fixed income",
        "volatility_index": "Volatility indexes",
        "other": "Other",
    }.get(str(asset_class), str(asset_class).replace("_", " ").title())
