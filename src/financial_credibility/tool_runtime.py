"""Execution runtime for registered agent tools."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from .aggregation import aggregate_scores
from .argument import classify_argument_type
from .asset_source_map import asset_source_plan
from .audit_agent import (
    audit_verification_chain,
    review_tool_surface,
    summarize_audit_report,
    summarize_evidence_pack,
)
from .audit import build_audit_trace as run_build_audit_trace
from .claim_verification import verify_atomic_claims
from .claims import decompose_claims
from .config import ToolkitConfig
from .data_sources import FreeDataSourceClient
from .entity import resolve_entity as run_resolve_entity
from .entity_extraction import extract_entities_from_memo as run_extract_entities_from_memo
from .extraction import EvidenceExtractor
from .facts import canonicalize_evidence, canonicalize_search_results
from .judges import create_judge
from .models import (
    ArgumentType,
    CanonicalFact,
    Evidence,
    EntityResolution,
    SearchResult,
    LicenseTag,
    SourceTier,
    SourceType,
    SupportLabel,
    to_plain,
)
from .modes.agentic import AgenticCredibilityRunner
from .preprocessing import preprocess_statement
from .price_history import format_price_history_summary, summarize_price_history
from .routing import route_sources as run_route_sources
from .rubrics import FACTUAL_TYPES
from .search import SearchClient
from .source_selection import selected_source_details, select_sources_for_claims as run_select_sources_for_claims
from .sources import assess_source
from .time_context import infer_time_context
from .tool_registry import get_registered_tool
from .toolkit import FinancialCredibilityToolkit
from .verification import verify_logic_claim as run_logic_verification
from .verification import verify_numeric_claim as run_numeric_verification
from .verification import verify_sources


ToolExecutor = Callable[[dict[str, Any], ToolkitConfig], dict[str, Any]]


def execute_tool(
    name: str,
    args: dict[str, Any] | None = None,
    config: ToolkitConfig | None = None,
) -> dict[str, Any]:
    """Execute a registered tool by name and return a JSON-compatible dict."""
    get_registered_tool(name)
    executors = _executors()
    if name not in executors:
        raise KeyError(f"No executor implemented for tool: {name}")
    return executors[name](dict(args or {}), config or ToolkitConfig.from_env())


def _executors() -> dict[str, ToolExecutor]:
    return {
        "preprocess_statement": _execute_preprocess_statement,
        "classify_claim": _execute_classify_claim,
        "extract_entities": _execute_extract_entities,
        "map_asset_sources": _execute_map_asset_sources,
        "load_source_documentation": _execute_load_source_documentation,
        "decompose_claims": _execute_decompose_claims,
        "resolve_entity": _execute_resolve_entity,
        "route_sources": _execute_route_sources,
        "select_sources": _execute_select_sources,
        "get_sec_company_facts": _execute_get_sec_company_facts,
        "get_recent_filings": _execute_get_recent_filings,
        "get_canonical_facts": _execute_get_canonical_facts,
        "get_company_fundamentals": _execute_get_company_fundamentals,
        "get_historical_prices": _execute_get_historical_prices,
        "compare_stock_performance": _execute_compare_stock_performance,
        "retrieve_evidence": _execute_retrieve_evidence,
        "verify_atomic_claim": _execute_verify_atomic_claim,
        "calibrate_uncertainty": _execute_calibrate_uncertainty,
        "build_audit_trace": _execute_build_audit_trace,
        "verify_numeric_claim": _execute_verify_numeric_claim,
        "verify_logic_claim": _execute_verify_logic_claim,
        "verify_source_quality": _execute_verify_source_quality,
        "aggregate_credibility": _execute_aggregate_credibility,
        "build_evidence_pack": _execute_build_evidence_pack,
        "audit_verification_chain": _execute_audit_verification_chain,
        "summarize_evidence_pack": _execute_summarize_evidence_pack,
        "summarize_audit_report": _execute_summarize_audit_report,
        "review_tool_surface": _execute_review_tool_surface,
    }


def _execute_preprocess_statement(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    result = preprocess_statement(_required_str(args, "statement"))
    return result.to_dict()


def _execute_classify_claim(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    classification = classify_argument_type(_required_str(args, "claim"))
    return to_plain(classification)


def _execute_extract_entities(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return run_extract_entities_from_memo(
        memo=_required_str(args, "memo"),
        config=config,
        max_entities=int(args.get("max_entities", 8)),
    )


def _execute_map_asset_sources(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    entities = args.get("entities")
    if not isinstance(entities, list):
        entities = run_extract_entities_from_memo(_required_str(args, "claim"), config=config).get("entities", [])
    return asset_source_plan(
        claim=_required_str(args, "claim"),
        entities=[item for item in entities if isinstance(item, dict)],
        include_planned=bool(args.get("include_planned_sources", True)),
    )


def _execute_load_source_documentation(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    source_ids = _source_ids_from_doc_args(args, config)
    include_planned = bool(args.get("include_planned_sources", False))
    details = selected_source_details(source_ids, include_planned=include_planned)
    found = {item["source_id"] for item in details}
    return {
        "source_ids": source_ids,
        "details": details,
        "missing_source_ids": [source_id for source_id in source_ids if source_id not in found],
    }


def _execute_decompose_claims(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return {"claims": [to_plain(item) for item in decompose_claims(_required_str(args, "claim"))]}


def _execute_resolve_entity(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    entity = run_resolve_entity(
        ticker=_required_str(args, "ticker"),
        evidence=_evidence_list_from_args(args),
        search_results=_search_result_list_from_args(args),
        cik=args.get("cik"),
        lei=args.get("lei"),
        figi=args.get("figi"),
    )
    return to_plain(entity)


def _execute_route_sources(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return run_route_sources(
        claim=_required_str(args, "claim"),
        official_only=bool(args.get("official_only", True)),
        asset_classes=_asset_classes_from_tool_args(args),
    )


def _execute_select_sources(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    claim = _required_str(args, "claim")
    classification = classify_argument_type(claim)
    if classification.argument_type not in FACTUAL_TYPES:
        return {
            "selections": [],
            "skipped": True,
            "reason": f"not_fact_checkable:{classification.argument_type.value}",
            "classification": to_plain(classification),
        }
    selections = run_select_sources_for_claims(
        claims=claim,
        config=config,
        candidate_limit=int(args.get("candidate_limit", 6)),
        max_selected=int(args.get("max_selected", 4)),
        include_planned=bool(args.get("include_planned_sources", False)),
        asset_classes=_asset_classes_from_tool_args(args),
        entities=[item for item in args.get("entities", []) if isinstance(item, dict)]
        if isinstance(args.get("entities"), list)
        else None,
    )
    return {"selections": selections}


def _execute_get_sec_company_facts(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    client = FreeDataSourceClient(config)
    results = client.sec_company_facts(
        claim=_required_str(args, "claim"),
        ticker=_required_str(args, "ticker"),
    )
    return {"results": [_search_result_to_dict(item) for item in results], "notes": []}


def _execute_get_recent_filings(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    client = FreeDataSourceClient(config)
    results = client.sec_recent_filings(_required_str(args, "ticker"))
    return {"results": [_search_result_to_dict(item) for item in results], "notes": []}


def _execute_get_canonical_facts(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    ticker = _required_str(args, "ticker")
    evidence = _evidence_list_from_args(args)
    search_results = _search_result_list_from_args(args)
    entity = run_resolve_entity(
        ticker=ticker,
        evidence=evidence,
        search_results=search_results,
        cik=args.get("cik"),
        lei=args.get("lei"),
    )
    facts = canonicalize_search_results(search_results, ticker, entity)
    if not facts:
        facts = canonicalize_evidence(evidence, ticker, entity)
    return {
        "entity_resolution": to_plain(entity),
        "canonical_facts": [to_plain(item) for item in facts],
    }


def _execute_get_company_fundamentals(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    ticker = _required_str(args, "ticker")
    client = FreeDataSourceClient(config)
    provider_calls = [
        ("alpha_vantage", lambda: client.alpha_vantage(ticker)),
        ("finnhub", lambda: client.finnhub(ticker)),
        ("fmp", lambda: client.fmp(ticker)),
    ]
    results: list[SearchResult] = []
    notes: list[str] = []
    for name, provider in provider_calls:
        try:
            provider_results = provider()
        except Exception as exc:
            notes.append(f"{name} failed: {exc}")
            continue
        results.extend(provider_results)
        if provider_results:
            notes.append(f"{name}: {len(provider_results)} result(s)")
    return {"results": [_search_result_to_dict(item) for item in _dedupe_results(results)], "notes": notes}


def _execute_get_historical_prices(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    ticker = _required_str(args, "ticker")
    start = _parse_date(_required_str(args, "start_date"))
    end = _parse_date(_required_str(args, "end_date"))
    return _historical_price_payload(ticker, start, end, config)


def _execute_compare_stock_performance(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    ticker = _required_str(args, "ticker")
    benchmark = _required_str(args, "benchmark_ticker")
    start = _parse_date(_required_str(args, "start_date"))
    end = _parse_date(_required_str(args, "end_date"))
    left = _historical_price_payload(ticker, start, end, config)
    right = _historical_price_payload(benchmark, start, end, config)

    if left.get("status") != "ok" or right.get("status") != "ok":
        return {
            "status": "insufficient",
            "ticker": ticker.upper(),
            "benchmark_ticker": benchmark.upper(),
            "ticker_result": left,
            "benchmark_result": right,
            "summary": "Could not retrieve both price histories.",
        }

    ticker_return = float(left["summary"]["total_return_pct"])
    benchmark_return = float(right["summary"]["total_return_pct"])
    relative = round(ticker_return - benchmark_return, 3)
    direction = "outperformed" if relative > 0 else "underperformed" if relative < 0 else "matched"
    return {
        "status": "ok",
        "ticker": ticker.upper(),
        "benchmark_ticker": benchmark.upper(),
        "ticker_return_pct": ticker_return,
        "benchmark_return_pct": benchmark_return,
        "relative_return_pct": relative,
        "summary": f"{ticker.upper()} {direction} {benchmark.upper()} by {abs(relative):.2f} percentage points.",
        "ticker_result": left,
        "benchmark_result": right,
    }


def _execute_retrieve_evidence(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    claim = _required_str(args, "claim")
    ticker = _required_str(args, "ticker")
    time_context = infer_time_context(claim, args.get("as_of_date"))
    as_of_date = time_context.effective_as_of_date or args.get("as_of_date")
    max_sources = int(args.get("max_sources", 8))
    classification = classify_argument_type(claim)
    if classification.argument_type not in FACTUAL_TYPES:
        return {
            "argument_type": classification.argument_type.value,
            "classification": to_plain(classification),
            "evidence": [],
            "search_notes": [f"retrieval skipped for non-factual claim type: {classification.argument_type.value}"],
            "extraction_notes": [],
            "time_context": time_context.to_dict(),
            "skipped": True,
        }
    results, search_notes = SearchClient(config).search_financial_sources(
        claim=claim,
        ticker=ticker,
        argument_type=classification.argument_type,
        max_sources=max_sources,
        as_of_date=as_of_date,
        prefetched_results=args.get("prefetched_results"),
        selected_sources=args.get("selected_sources"),
    )
    evidence, extraction_notes = EvidenceExtractor(config).extract(
        claim=claim,
        ticker=ticker,
        search_results=results,
        as_of_date=as_of_date or date.today().isoformat(),
        max_sources=max_sources,
    )
    return {
        "argument_type": classification.argument_type.value,
        "classification": to_plain(classification),
        "evidence": [_evidence_to_dict(item) for item in evidence],
        "search_notes": search_notes,
        "extraction_notes": extraction_notes,
        "time_context": time_context.to_dict(),
    }


def _execute_verify_atomic_claim(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    claim = _required_str(args, "claim")
    classification = classify_argument_type(claim)
    if classification.argument_type not in FACTUAL_TYPES:
        return {
            "atomic_claims": [
                {
                    "atomic_claim": {
                        "claim_id": "claim_1",
                        "text": claim,
                        "argument_type": classification.argument_type.value,
                        "classification_confidence": classification.confidence,
                        "signals": classification.signals,
                    },
                    "verdict": "not_applicable",
                    "evidence_urls": [],
                    "evidence_keys": [],
                    "canonical_fact_ids": [],
                    "numeric_derivation": None,
                    "confidence_components": None,
                    "human_review_required": False,
                    "review_reasons": [],
                    "issues": [f"Skipped non-factual claim type: {classification.argument_type.value}"],
                }
            ],
            "skipped": True,
            "reason": f"not_fact_checkable:{classification.argument_type.value}",
            "classification": to_plain(classification),
        }
    ticker = _required_str(args, "ticker")
    evidence = _evidence_list_from_args(args)
    facts = _canonical_fact_list_from_args(args)
    entity = run_resolve_entity(ticker=ticker, evidence=evidence, cik=args.get("cik"), lei=args.get("lei"))
    if not facts:
        facts = canonicalize_evidence(evidence, ticker, entity)
    results = verify_atomic_claims(
        claim=claim,
        evidence=evidence,
        canonical_facts=facts,
        entity_resolution=entity,
        judge=create_judge(config),
    )
    return {"atomic_claims": [to_plain(item) for item in results]}


def _execute_calibrate_uncertainty(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return _execute_verify_atomic_claim(args, config)


def _execute_build_audit_trace(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    ticker = _required_str(args, "ticker")
    claim = _required_str(args, "claim")
    as_of_date = str(args.get("as_of_date") or date.today().isoformat())
    search_results = _search_result_list_from_args(args)
    evidence = _evidence_list_from_args(args)
    facts = _canonical_fact_list_from_args(args)
    entity = run_resolve_entity(ticker=ticker, evidence=evidence, search_results=search_results)
    if not facts:
        facts = canonicalize_search_results(search_results, ticker, entity) or canonicalize_evidence(evidence, ticker, entity)
    atomic_results = verify_atomic_claims(claim, evidence, facts, entity, create_judge(config))
    trace = run_build_audit_trace(
        claim=claim,
        ticker=ticker,
        as_of_date=as_of_date,
        search_results=search_results,
        evidence=evidence,
        canonical_facts=facts,
        entity_resolution=entity,
        atomic_results=atomic_results,
        search_notes=[],
        extraction_notes=[],
    )
    return to_plain(trace)


def _execute_verify_numeric_claim(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    check = run_numeric_verification(
        claim=_required_str(args, "claim"),
        evidence=_evidence_list_from_args(args),
        judge=create_judge(config),
    )
    return to_plain(check)


def _execute_verify_logic_claim(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    claim = _required_str(args, "claim")
    argument_type = _argument_type(args.get("argument_type"), claim)
    check = run_logic_verification(
        claim=claim,
        evidence=_evidence_list_from_args(args),
        argument_type=argument_type,
        judge=create_judge(config),
    )
    return to_plain(check)


def _execute_verify_source_quality(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    evidence = _evidence_list_from_args(args)
    argument_type = _argument_type(args.get("argument_type"), "")
    breakdown, _, _, _ = aggregate_scores(argument_type, evidence, [])
    return to_plain(verify_sources(evidence, breakdown))


def _execute_aggregate_credibility(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    evidence = _evidence_list_from_args(args)
    argument_type = _argument_type(args.get("argument_type"), "")
    breakdown, verdict, label, risk_flags = aggregate_scores(
        argument_type,
        evidence,
        args.get("risk_flags") or [],
    )
    return {
        "score_breakdown": to_plain(breakdown),
        "verdict": verdict.value,
        "credibility_label": label.value,
        "risk_flags": risk_flags,
    }


def _execute_build_evidence_pack(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    toolkit = FinancialCredibilityToolkit(config)
    mode = str(args.get("mode", "agentic"))
    kwargs = {
        "claim": _required_str(args, "claim"),
        "ticker": _required_str(args, "ticker"),
        "as_of_date": args.get("as_of_date"),
        "max_sources": int(args.get("max_sources", 8)),
        "prefetched_results": args.get("prefetched_results"),
    }
    if mode == "agentic":
        pack = AgenticCredibilityRunner(toolkit).run(**kwargs)
    else:
        pack = toolkit.build_evidence_pack(**kwargs, mode="strict")
    return pack.to_dict()


def _execute_audit_verification_chain(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    report = audit_verification_chain(
        report_payload=args.get("report_payload"),
        evidence_pack=args.get("evidence_pack"),
        audit_trace=args.get("audit_trace"),
        agent_trace=args.get("agent_trace"),
        outcome_reference=args.get("outcome_reference"),
        config=config,
    )
    return to_plain(report)


def _execute_summarize_evidence_pack(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return summarize_evidence_pack(
        report_payload=args.get("report_payload"),
        evidence_pack=args.get("evidence_pack"),
    )


def _execute_summarize_audit_report(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return summarize_audit_report(args.get("audit_report") or {})


def _execute_review_tool_surface(args: dict[str, Any], config: ToolkitConfig) -> dict[str, Any]:
    return review_tool_surface(args.get("profile"))


def _historical_price_payload(
    ticker: str,
    start: date,
    end: date,
    config: ToolkitConfig,
) -> dict[str, Any]:
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    client = FreeDataSourceClient(config)
    providers = [
        ("Alpha Vantage", "alpha_vantage_historical_prices", client.alpha_vantage_historical_prices),
        ("Financial Modeling Prep", "fmp_historical_prices", client.fmp_historical_prices),
        ("Finnhub", "finnhub_historical_prices", client.finnhub_historical_prices),
    ]
    fred_provider = getattr(client, "fred_historical_prices", None)
    if callable(fred_provider):
        providers.append(("FRED", "fred_historical_prices", fred_provider))
    providers.append(("Stooq", "stooq_historical_prices", client.stooq_historical_prices))
    errors = []
    for provider_label, provider_name, provider in providers:
        try:
            points = provider(ticker, start, end)
        except Exception as exc:
            errors.append(f"{provider_name} failed: {exc}")
            continue
        summary = summarize_price_history(points)
        if summary is None:
            errors.append(f"{provider_name}: no usable price history")
            continue
        months = max(1, round((end - start).days / 30.5))
        url = client._price_history_url(provider_name, ticker, start, end)
        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "provider": provider_label,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "summary": summary.__dict__,
            "evidence_text": format_price_history_summary(ticker, months, summary),
            "evidence_url": url,
        }

    return {
        "status": "insufficient",
        "ticker": ticker.upper(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "summary": {},
        "evidence_text": "",
        "evidence_url": "",
        "errors": errors,
    }


def _evidence_list_from_args(args: dict[str, Any]) -> list[Evidence]:
    return [_evidence_from_dict(item) for item in args.get("evidence", [])]


def _search_result_list_from_args(args: dict[str, Any]) -> list[SearchResult]:
    return [_search_result_from_dict(item) for item in args.get("search_results", [])]


def _canonical_fact_list_from_args(args: dict[str, Any]) -> list[CanonicalFact]:
    return [_canonical_fact_from_dict(item) for item in args.get("canonical_facts", [])]


def _asset_classes_from_tool_args(args: dict[str, Any]) -> list[str] | None:
    values = []
    raw_asset_classes = args.get("asset_classes")
    if isinstance(raw_asset_classes, str):
        values.append(raw_asset_classes)
    elif isinstance(raw_asset_classes, list):
        values.extend(str(item) for item in raw_asset_classes if item)
    raw_entities = args.get("entities")
    if isinstance(raw_entities, list):
        values.extend(
            str(item.get("asset_class"))
            for item in raw_entities
            if isinstance(item, dict) and item.get("asset_class")
        )
    deduped = list(dict.fromkeys(item.strip() for item in values if item and item.strip()))
    return deduped or None


def _source_ids_from_doc_args(args: dict[str, Any], config: ToolkitConfig) -> list[str]:
    values = []
    raw_source_ids = args.get("source_ids")
    if isinstance(raw_source_ids, str):
        values.append(raw_source_ids)
    elif isinstance(raw_source_ids, list):
        values.extend(str(item) for item in raw_source_ids if item)
    if args.get("source_id"):
        values.append(str(args["source_id"]))
    if not values and args.get("claim"):
        selections = run_select_sources_for_claims(
            claims=str(args["claim"]),
            config=config,
            candidate_limit=int(args.get("candidate_limit", 6)),
            max_selected=int(args.get("max_selected", 4)),
            include_planned=bool(args.get("include_planned_sources", False)),
            asset_classes=_asset_classes_from_tool_args(args),
            entities=[item for item in args.get("entities", []) if isinstance(item, dict)]
            if isinstance(args.get("entities"), list)
            else None,
        )
        for selection in selections:
            values.extend(selection.get("selected_sources") or [])
    return list(dict.fromkeys(item.strip() for item in values if item and item.strip()))


def _evidence_from_dict(item: dict[str, Any]) -> Evidence:
    source = assess_source(str(item.get("url", "")), str(item.get("title", "")))
    source_type = _enum_value(SourceType, item.get("source_type"), source.source_type)
    source_tier = _enum_value(SourceTier, item.get("source_tier"), source.source_tier)
    support_label = _enum_value(SupportLabel, item.get("support_label"), SupportLabel.NOT_ENOUGH_INFO)
    return Evidence(
        url=str(item.get("url", "")),
        title=str(item.get("title", "")),
        text=str(item.get("text") or item.get("snippet") or ""),
        source_type=source_type,
        source_tier=source_tier,
        domain=str(item.get("domain") or source.domain),
        published_at=item.get("published_at"),
        license_tag=_enum_value(LicenseTag, item.get("license_tag"), source.license_tag),
        is_official_primary=bool(item.get("is_official_primary", source.is_official_primary)),
        source_authority=float(item.get("source_authority", source.authority_score)),
        recency_score=float(item.get("recency_score", 0.0)),
        relevance_score=float(item.get("relevance_score", 0.0)),
        entity_match_score=float(item.get("entity_match_score", 0.0)),
        numeric_consistency_score=float(item.get("numeric_consistency_score", 0.0)),
        support_label=support_label,
        support_score=float(item.get("support_score", 0.0)),
        reasoning_quality_score=float(item.get("reasoning_quality_score", 0.0)),
        independence_score=float(item.get("independence_score", 0.0)),
        notes=[str(note) for note in item.get("notes", [])],
    )


def _search_result_to_dict(item: SearchResult) -> dict[str, Any]:
    return to_plain(item)


def _search_result_from_dict(item: dict[str, Any]) -> SearchResult:
    return SearchResult(
        title=str(item.get("title", "")),
        url=str(item.get("url") or item.get("link") or ""),
        snippet=str(item.get("snippet") or item.get("text") or ""),
        published_at=item.get("published_at") or item.get("date"),
        source=item.get("source"),
        raw=dict(item.get("raw") or {k: v for k, v in item.items() if k not in {"title", "url", "snippet", "text"}}),
    )


def _evidence_to_dict(item: Evidence) -> dict[str, Any]:
    return to_plain(item)


def _canonical_fact_from_dict(item: dict[str, Any]) -> CanonicalFact:
    return CanonicalFact(
        fact_id=str(item.get("fact_id", "")),
        source_type=_enum_value(SourceType, item.get("source_type"), SourceType.UNKNOWN),
        authority_tier=_enum_value(SourceTier, item.get("authority_tier"), SourceTier.T4),
        license_tag=_enum_value(LicenseTag, item.get("license_tag"), LicenseTag.UNKNOWN),
        entity_id=str(item.get("entity_id", "")),
        ticker=str(item.get("ticker", "")).upper(),
        cik=item.get("cik"),
        lei=item.get("lei"),
        report_period=item.get("report_period"),
        filing_date=item.get("filing_date"),
        observation_date=item.get("observation_date"),
        vintage_date=item.get("vintage_date"),
        unit=item.get("unit"),
        currency=item.get("currency"),
        fact_name=item.get("fact_name"),
        value=item.get("value"),
        provenance_locator=str(item.get("provenance_locator", "")),
        parser_confidence=float(item.get("parser_confidence", 0.0)),
        raw=dict(item.get("raw") or {}),
    )


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen = set()
    deduped = []
    for item in results:
        if not item.url or item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)
    return deduped


def _argument_type(value: Any, claim: str) -> ArgumentType:
    if value:
        try:
            return ArgumentType(str(value))
        except ValueError:
            pass
    if claim:
        return classify_argument_type(claim).argument_type
    return ArgumentType.OPINION_ANALYSIS


def _enum_value(enum_cls, value: Any, default):
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _required_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing required argument: {key}")
    return str(value)
