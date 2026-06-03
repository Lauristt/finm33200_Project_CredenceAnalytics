"""Report payload and Markdown rendering for memo-level verification."""

from __future__ import annotations

from statistics import mean
from typing import Any, Callable

from .config import ToolkitConfig
from .claims import decompose_claims
from .entity_extraction import extract_entities_from_memo, is_contextual_non_ticker_token
from .errors import UserFacingError
from .explanations import build_claim_explanation, explain_review_reasons, generate_llm_claim_summaries
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
    source_results: list[dict[str, Any]] | None = None,
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
            source_results=source_results,
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
    # Macro entities (CPI, GDP, PCE, etc.) have no SEC ticker but can be verified
    # against FRED / BLS / BEA / EIA / ECB / BIS / IMF / WorldBank time-series.
    macro_entities = [
        e for e in entity_extraction.get("entities", [])
        if e.get("asset_class") in _MACRO_ASSET_CLASSES and not e.get("ticker")
    ]

    if not clean_tickers and not macro_entities:
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
        _enhance_payload(payload, cfg)
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

    # Macro verification branch — runs before equity so progress trace is sequential
    for entity in macro_entities:
        symbol = str(entity.get("symbol") or entity.get("name") or "MACRO")
        try:
            macro_run = _run_macro_verification(
                memo=memo,
                entity=entity,
                toolkit=toolkit,
                as_of_date=effective_as_of_date,
                trace_callback=_scoped_progress(progress_callback, symbol),
            )
            runs.append(macro_run)
        except Exception as exc:
            errors.append({"ticker": symbol, "error": str(exc)})
            _emit_progress(
                progress_callback, "run_entity", "error",
                f"Macro verification failed for {symbol}: {exc}",
                outputs={"ticker": symbol},
            )

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
                source_results=source_results,
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
    _enhance_payload(payload, cfg)
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
    """Render a user-facing Markdown report, keeping internal trace noise out."""
    summary = payload.get("summary", {})
    lines = [
        "# Credence Verification Report",
        "",
        "## Bottom Line",
        "",
        _bottom_line_sentence(summary),
        "",
    ]

    scope_note = _scope_note(payload)
    if scope_note:
        lines.extend(["## Scope", "", scope_note, ""])

    if payload.get("errors"):
        lines.extend(["## Errors", ""])
        for error in payload["errors"]:
            lines.append(f"- {error.get('ticker')}: {error.get('error')}")
        lines.append("")

    for run in payload.get("runs", []):
        ticker = run.get("ticker", "")
        lines.extend([f"## {ticker}", ""])
        checked_results = [result for result in run.get("atomic_claims", []) if not _is_skipped_result(result)]
        skipped_results = [result for result in run.get("atomic_claims", []) if _is_skipped_result(result)]

        explanations = {
            item.get("claim_id"): item
            for item in run.get("claim_explanations") or []
            if item.get("claim_id")
        }
        evidence_by_url = {item.get("url", ""): item for item in run.get("evidence", []) if item.get("url")}
        if not checked_results and not skipped_results:
            lines.append("No fact-checkable claim was produced for this entity.")
            lines.append("")

        for result in checked_results:
            claim = (result.get("atomic_claim") or {}).get("text", "")
            explanation = explanations.get((result.get("atomic_claim") or {}).get("claim_id"))
            lines.append(_claim_result_sentence(claim, result, explanation, evidence_by_url))

        if skipped_results:
            if checked_results:
                lines.append("")
            lines.append("Not fact-checked:")
            for result in skipped_results:
                claim = (result.get("atomic_claim") or {}).get("text", "")
                claim_type = (result.get("atomic_claim") or {}).get("argument_type", "n/a")
                lines.append(f"- Skipped `{claim_type}`: {claim}")

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _enhance_payload(payload: dict[str, Any], config: Any = None) -> None:
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
        # Enrich each atomic claim with LLM-generated narrative summaries.
        if config:
            all_facts = run.get("canonical_facts") or []
            for result in run.get("atomic_claims", []):
                if _is_skipped_result(result):
                    continue
                summaries = generate_llm_claim_summaries(result, all_facts, config)
                result.update(summaries)


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


def _bottom_line_sentence(summary: dict[str, Any]) -> str:
    entities = int(summary.get("entity_count") or 0)
    claims = int(summary.get("atomic_claim_count") or 0)
    skipped = int(summary.get("skipped_claim_count") or 0)
    review = int(summary.get("human_review_count") or 0)
    pieces = [f"Checked {claims} fact-checkable claim{'s' if claims != 1 else ''} across {entities} entit{'ies' if entities != 1 else 'y'}."]
    if skipped:
        pieces.append(f"Skipped {skipped} opinion, forecast, or non-falsifiable statement{'s' if skipped != 1 else ''}.")
    if review:
        pieces.append(f"{review} claim{'s' if review != 1 else ''} {'need' if review != 1 else 'needs'} human review.")
    else:
        pieces.append("No claim was flagged for mandatory human review.")
    return " ".join(pieces)


def _scope_note(payload: dict[str, Any]) -> str:
    coverage = payload.get("coverage_summary") or {}
    detected_only = coverage.get("detected_only_entities") or []
    if not detected_only:
        return ""
    grouped: dict[str, list[str]] = {}
    for item in detected_only:
        label = str(item.get("label") or item.get("symbol") or item.get("ticker") or "").strip()
        asset_class = _asset_class_label(str(item.get("asset_class") or "other"))
        if label:
            grouped.setdefault(asset_class, []).append(label)
    if not grouped:
        return ""
    fragments = [
        f"{asset_class}: {', '.join(labels[:5])}{'...' if len(labels) > 5 else ''}"
        for asset_class, labels in grouped.items()
    ]
    return "Detected but not fully checked in this run: " + "; ".join(fragments) + "."


def _claim_result_sentence(
    claim: str,
    result: dict[str, Any],
    explanation: dict[str, Any] | None,
    evidence_by_url: dict[str, dict[str, Any]],
) -> str:
    verdict = _report_verdict_label(result.get("verdict"))
    source = _best_evidence_for_result(result, evidence_by_url)
    reason = _explanation_sentence(explanation)
    if not reason:
        reason = _fallback_reason_sentence(result, source)
    review = _review_sentence(result.get("review_reasons") or [])
    parts = [f"- **{verdict}.** {_sentence_text(claim)}"]
    if source:
        parts.append(f"Evidence: {_source_label(source)}.")
    if reason:
        parts.append(f"Reason: {reason}")
    if review:
        parts.append(review)
    return " ".join(parts)


def _sentence_text(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?", "。", "！", "？")) else text + "."


def _report_verdict_label(value: Any) -> str:
    text = str(value or "").lower()
    if "contradict" in text:
        return "Inconsistent"
    if "insufficient" in text or "not_found" in text or "weak" in text:
        return "Insufficient evidence"
    if "partial" in text:
        return "Partially consistent"
    if "support" in text or "verified" in text:
        return "Consistent"
    if "not_applicable" in text:
        return "Not fact-checkable"
    return str(value or "n/a")


def _best_evidence_for_result(result: dict[str, Any], evidence_by_url: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for url in result.get("evidence_urls") or []:
        if url in evidence_by_url:
            return evidence_by_url[url]
    return None


def _source_label(source: dict[str, Any]) -> str:
    title = str(source.get("title") or source.get("domain") or "source")
    domain = str(source.get("domain") or "").strip()
    tier = str(source.get("source_tier") or "").strip()
    suffix = f" ({domain})" if domain else ""
    prefix = f"{tier} " if tier else ""
    return f"{prefix}{title}{suffix}"


def _fallback_reason_sentence(result: dict[str, Any], source: dict[str, Any] | None) -> str:
    verdict = str(result.get("verdict") or "").lower()
    issues = [str(issue) for issue in (result.get("issues") or [])]
    review_reasons = {str(reason) for reason in (result.get("review_reasons") or [])}
    if "insufficient" in verdict and source:
        if "ambiguous_unit_currency_or_period" in review_reasons:
            return "Evidence was retrieved, but the exact value, unit, or reporting period was not matched clearly."
        return "Evidence was retrieved, but it was not sufficient to verify the claim."
    if "partial" in verdict and "ambiguous_unit_currency_or_period" in review_reasons:
        return "The source supports part of the claim, but at least one value, unit, or reporting period remains ambiguous."
    if any("unmatched claim numbers" in issue for issue in issues):
        return "Some numbers in the claim were not matched in the retrieved evidence."
    return ""


def _explanation_sentence(explanation: dict[str, Any] | None) -> str:
    if not explanation:
        return ""
    numeric = _natural_numeric_report_sentence(str(explanation.get("numeric_summary") or ""))
    if numeric and not numeric.lower().startswith("no deterministic numeric"):
        return numeric
    summary = _clean_report_sentence(str(explanation.get("summary") or ""))
    if summary:
        return summary
    source = _clean_report_sentence(str(explanation.get("source_summary") or ""))
    if source and not source.lower().startswith("the main evidence is"):
        return source
    return ""


def _natural_numeric_report_sentence(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    lower = text.lower()
    if "numeric derivation" in lower and "passed" in lower:
        return "Numeric check passed."
    if "numeric derivation" in lower and "did not pass" in lower:
        return "Numeric check did not match the claim."
    return _clean_report_sentence(text)


def _clean_report_sentence(value: str) -> str:
    text = " ".join(str(value or "").split())
    blocked_fragments = (
        "HTTP Error",
        "fallback:",
        "matched ",
        "unmatched claim numbers:",
        "numeric_match_summary",
        "llm_judge_unavailable",
        "ticker_only_entity_resolution",
    )
    if any(fragment in text for fragment in blocked_fragments):
        return ""
    if text.startswith("The claim is marked"):
        return ""
    import re

    text = re.sub(r"\s+with confidence\s+\d+(?:\.\d+)?", "", text)
    return text


def _review_sentence(reasons: list[str]) -> str:
    labels = [_review_reason_label(reason) for reason in reasons[:2]]
    labels = [label for label in labels if label]
    if not labels:
        return ""
    return "Needs human review: " + ", ".join(labels) + "."


def _review_reason_label(value: str) -> str:
    return {
        "no_official_primary_source": "no official primary source was found",
        "non_official_sources_only": "only supplemental or third-party sources were available",
        "official_source_conflict": "official sources conflict",
        "amended_or_restatement_or_vintage_revision": "an amendment, restatement, or vintage revision may matter",
        "low_entity_resolution_confidence": "entity resolution is uncertain",
        "low_retrieval_sufficiency": "retrieved evidence is limited",
        "ambiguous_unit_currency_or_period": "the unit, currency, or period is ambiguous",
        "explanation_claim_needs_human_review": "the explanatory claim needs human judgment",
    }.get(str(value), str(value).replace("_", " "))


def _source_line_for_run(run: dict[str, Any], checked_results: list[dict[str, Any]]) -> str:
    used_urls = {
        url
        for result in checked_results
        for url in (result.get("evidence_urls") or [])
    }
    sources = [
        source
        for source in run.get("evidence", [])
        if source.get("url") in used_urls
    ]
    if not sources:
        sources = (run.get("evidence") or [])[:2]
    if not sources:
        return ""
    labels = [_source_label(source) for source in sources[:3]]
    return "Sources used: " + "; ".join(labels) + "."


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
    source_results: list[dict[str, Any]] | None,
    trace_callback: Callable[[dict[str, Any]], None] | None = None,
) -> EvidencePack:
    kwargs = {
        "claim": memo,
        "ticker": ticker,
        "as_of_date": as_of_date,
        "max_sources": max_sources,
        "prefetched_results": prefetched_results,
        "source_results": source_results,
    }
    if mode == "strict":
        return toolkit.build_evidence_pack(**kwargs, mode="strict", trace_callback=trace_callback)
    return AgenticCredibilityRunner(toolkit).run(**kwargs, trace_callback=trace_callback)


def _is_multi_tool_mode(mode: str) -> bool:
    return str(mode or "").replace("-", "_").lower() == "multi_tool"


# ---------------------------------------------------------------------------
# Macro indicator verification (FRED / BLS / BEA / EIA / ECB / BIS / IMF / WB)
# ---------------------------------------------------------------------------

_MACRO_ASSET_CLASSES = {
    "macro_indicator",
    "rates",
    "commodity",          # entity_extraction uses singular form
    "commodity_future",
    "fx",
    "crypto",
    "credit",
    "fixed_income",
}

_MACRO_PROVIDERS = [
    "fred",
    "bls_api",
    "bea_api",
    "eia_api",
    "ecb_data_portal",
    "bis_data_portal",
    "imf_data_api",
    "world_bank_indicators",
]


def _bls_period_to_iso(date_str: str) -> str | None:
    """Convert BLS period label '2024-M01' → '2024-01-01'. Returns None if unparseable."""
    import re as _re
    m = _re.match(r"(\d{4})-M(\d{2})$", str(date_str or ""))
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    # Quarterly format 'YYYY-QN' → first month of quarter
    q = _re.match(r"(\d{4})-Q(\d)$", str(date_str or ""))
    if q:
        month = str((int(q.group(2)) - 1) * 3 + 1).zfill(2)
        return f"{q.group(1)}-{month}-01"
    # Already ISO or close enough
    if _re.match(r"\d{4}-\d{2}-\d{2}", str(date_str or "")):
        return str(date_str)[:10]
    return None


def _macro_canonical_facts(
    results: list[Any],
    symbol: str,
) -> list[Any]:
    """Convert SearchResult objects from macro providers into CanonicalFact objects."""
    from .models import CanonicalFact, SourceType, SourceTier, LicenseTag

    facts: list[Any] = []
    for result in results:
        raw = result.raw if hasattr(result, "raw") else (result.get("raw") or {})
        provider = raw.get("provider", "")
        series_id = raw.get("series_id", symbol)
        # Use the result title as fact_name so token overlap with the claim works.
        # E.g. "BLS CPI for all urban consumers (CUSR0000SA0)" → contains "cpi"
        result_title = (getattr(result, "title", "") or "").strip()
        fact_label = result_title if result_title else series_id
        result_url = getattr(result, "url", "") or ""

        if provider == "fred":
            for obs in raw.get("observations", []):
                date_str = obs.get("date", "")
                val_str = str(obs.get("value", ""))
                if not date_str or val_str in {"", ".", None}:
                    continue
                try:
                    value = float(val_str)
                except (ValueError, TypeError):
                    continue
                facts.append(CanonicalFact(
                    fact_id=f"fred_{series_id}_{date_str}",
                    source_type=SourceType.REGULATOR_EXCHANGE,
                    authority_tier=SourceTier.T1,
                    license_tag=LicenseTag.PUBLIC_OFFICIAL,
                    entity_id=series_id,
                    ticker=symbol,
                    report_period=date_str[:10],
                    fact_name=fact_label,
                    value=value,
                    provenance_locator=result_url,
                    parser_confidence=0.95,
                    raw={"provider": "fred", "series_id": series_id, "period_kind": "monthly"},
                ))

        elif provider == "bls_api":
            for row in raw.get("rows", []):
                iso = _bls_period_to_iso(row.get("date", ""))
                val_str = str(row.get("value", ""))
                if not iso or not val_str:
                    continue
                try:
                    value = float(val_str)
                except (ValueError, TypeError):
                    continue
                facts.append(CanonicalFact(
                    fact_id=f"bls_{series_id}_{iso}",
                    source_type=SourceType.REGULATOR_EXCHANGE,
                    authority_tier=SourceTier.T1,
                    license_tag=LicenseTag.PUBLIC_OFFICIAL,
                    entity_id=series_id,
                    ticker=symbol,
                    report_period=iso,
                    fact_name=fact_label,
                    value=value,
                    provenance_locator=result_url,
                    parser_confidence=0.95,
                    raw={"provider": "bls_api", "series_id": series_id, "period_kind": "monthly"},
                ))

        elif provider in {"bea_api", "eia_api", "ecb_data_portal", "bis_data_portal",
                          "imf_data_api", "world_bank_indicators"}:
            # Generic path: rows with {date, value} keys
            period_kind = "quarterly" if provider == "bea_api" else "monthly"
            for row in raw.get("rows", raw.get("observations", [])):
                iso = _bls_period_to_iso(row.get("date", "")) or str(row.get("date", ""))[:10]
                val_str = str(row.get("value", ""))
                if not iso or len(iso) < 7 or not val_str:
                    continue
                try:
                    value = float(val_str)
                except (ValueError, TypeError):
                    continue
                facts.append(CanonicalFact(
                    fact_id=f"{provider}_{series_id}_{iso}",
                    source_type=SourceType.REGULATOR_EXCHANGE,
                    authority_tier=SourceTier.T1,
                    license_tag=LicenseTag.PUBLIC_OFFICIAL,
                    entity_id=series_id,
                    ticker=symbol,
                    report_period=iso,
                    fact_name=fact_label,
                    value=value,
                    provenance_locator=result_url,
                    parser_confidence=0.90,
                    raw={"provider": provider, "series_id": series_id, "period_kind": period_kind},
                ))

    return facts


def _run_macro_verification(
    memo: str,
    entity: dict[str, Any],
    toolkit: FinancialCredibilityToolkit,
    as_of_date: str | None,
    trace_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Fetch macro time-series from FRED/BLS/etc. and run claim verification."""
    from .claim_verification import verify_atomic_claims
    from .claims import decompose_claims
    from .rubrics import FACTUAL_TYPES
    from .judges import create_judge
    from .models import to_plain, ArgumentType, Verdict, CredibilityLabel, VerificationVerdict, EntityResolution
    from .data_sources import FreeDataSourceClient

    symbol = str(entity.get("symbol") or entity.get("name") or "MACRO")
    name = str(entity.get("name") or symbol)

    _emit_progress(trace_callback, "run_entity", "running", f"Starting macro verification for {symbol}.")

    # Anchor the fetch window to the year mentioned in the claim so BLS/FRED
    # include the right historical period (e.g. "January 2024" → end=2024-12-31).
    import re as _re
    from .time_context import infer_time_context as _itc
    claim_tc = _itc(memo, as_of_date)
    effective_fetch_date = claim_tc.effective_as_of_date or as_of_date
    if not effective_fetch_date:
        year_m = _re.search(r"\b(20\d{2})\b", memo)
        if year_m:
            effective_fetch_date = f"{year_m.group(1)}-12-31"

    # Fetch from all macro-relevant providers with extra history for YoY.
    # Pass symbol_hint so FRED/EIA can look up the right series directly
    # rather than relying on fuzzy keyword matching in the claim text.
    client = FreeDataSourceClient(toolkit.config)
    results: list[Any] = []
    for provider_name, fetcher in [
        ("fred",               lambda: client.fred(memo, as_of_date=effective_fetch_date, limit=24, symbol_hint=symbol)),
        ("bls_api",            lambda: client.bls_api(memo, as_of_date=effective_fetch_date)),
        ("bea_api",            lambda: client.bea_api(memo, as_of_date=effective_fetch_date)),
        ("eia_api",            lambda: client.eia_api(memo, as_of_date=effective_fetch_date, symbol_hint=symbol)),
        ("ecb_data_portal",    lambda: client.ecb_data_portal(memo)),
        ("bis_data_portal",    lambda: client.bis_data_portal(memo)),
        ("imf_data_api",       lambda: client.imf_data_api(memo)),
        ("world_bank_indicators", lambda: client.world_bank_indicators(memo)),
    ]:
        try:
            fetched = fetcher()
            results.extend(fetched)
        except Exception:
            pass

    canonical_facts = _macro_canonical_facts(results, symbol)

    _emit_progress(
        trace_callback, "canonicalize_facts", "ok",
        f"Converted {len(canonical_facts)} macro observations to canonical facts.",
        outputs={"fact_count": len(canonical_facts), "symbol": symbol},
    )

    atomic_claims = decompose_claims(memo)
    fact_checkable = [c for c in atomic_claims if c.argument_type in FACTUAL_TYPES]
    judge = toolkit.judge

    macro_entity_resolution = EntityResolution(ticker=symbol, entity_id=symbol, confidence=0.85)
    claim_results = verify_atomic_claims(
        claim=memo,
        evidence=[],
        canonical_facts=canonical_facts,
        entity_resolution=macro_entity_resolution,
        judge=judge,
    )

    _emit_progress(
        trace_callback, "verify_atomic_claims", "ok",
        f"Verified {len(claim_results)} atomic claim(s) for {symbol}.",
    )

    # Compute overall verdict from atomic results
    verdicts = [r.verdict.value if hasattr(r.verdict, "value") else str(r.verdict) for r in claim_results]
    if any(v == VerificationVerdict.CONTRADICTED.value for v in verdicts):
        overall_verdict = Verdict.CONTRADICTED
        credibility_label = CredibilityLabel.CONTRADICTED_FACT
        credibility_score = 0.15
    elif any(v in {VerificationVerdict.SUPPORTED.value, VerificationVerdict.VERIFIED.value,
                   VerificationVerdict.PARTIALLY_VERIFIED.value} for v in verdicts):
        overall_verdict = Verdict.SUPPORTED
        credibility_label = CredibilityLabel.HIGH
        credibility_score = 0.80
    else:
        overall_verdict = Verdict.INSUFFICIENT
        credibility_label = CredibilityLabel.LOW
        credibility_score = 0.40

    _emit_progress(trace_callback, "run_entity", "ok", f"Finished macro verification for {symbol}.")

    return {
        "claim": memo,
        "ticker": symbol,
        "entity_name": name,
        "asset_class": entity.get("asset_class", "macro_indicator"),
        "as_of_date": as_of_date or "",
        "argument_type": ArgumentType.METRIC_FACT.value,
        "classification_confidence": 0.85,
        "verdict": overall_verdict.value,
        "credibility_label": credibility_label.value,
        "credibility_score": credibility_score,
        "score_breakdown": {},
        "atomic_claims": [to_plain(r) for r in claim_results],
        "canonical_facts": [to_plain(f) for f in canonical_facts],
        "evidence": [{"title": getattr(r, "title", ""), "url": getattr(r, "url", ""),
                      "source": getattr(r, "source", ""), "snippet": getattr(r, "snippet", "")}
                     for r in results],
        "risk_flags": [] if canonical_facts else ["no_macro_data_found"],
        "mode": "macro",
        "metadata": {"providers_queried": _MACRO_PROVIDERS, "fact_count": len(canonical_facts)},
    }


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
