"""Independent audit checks for credibility reports and agent traces."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .argument import classify_argument_type
from .judges import create_judge
from .models import (
    ArgumentType,
    AuditFinding,
    AuditReport,
    Evidence,
    LicenseTag,
    SourceTier,
    SourceType,
    SupportLabel,
    VerificationVerdict,
    to_plain,
)
from .price_history import needs_historical_price_data
from .rubrics import FACTUAL_TYPES
from .sources import assess_source


SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "critical": 3}


def audit_verification_chain(
    report_payload: dict[str, Any] | None = None,
    evidence_pack: dict[str, Any] | Any | None = None,
    audit_trace: dict[str, Any] | Any | None = None,
    agent_trace: dict[str, Any] | Any | None = None,
    outcome_reference: dict[str, Any] | None = None,
    config=None,
) -> AuditReport:
    """Audit evidence, computation, tool use, constraints, and optional outcomes."""
    report = to_plain(report_payload or {})
    pack = to_plain(evidence_pack or {})
    replay_trace = to_plain(audit_trace or {})
    behavior_trace = to_plain(agent_trace or {})
    findings: list[AuditFinding] = []

    findings.extend(_audit_evidence(report, pack))
    findings.extend(_audit_common_sense(report, pack))
    findings.extend(_audit_computation(report, pack))
    findings.extend(_audit_tool_use(behavior_trace, report, replay_trace))
    findings.extend(_audit_constraints(report, pack))
    findings.extend(_audit_reasoning(report, pack, config))
    findings.extend(_audit_prompt(behavior_trace))
    findings.extend(_audit_tool_surface_trace(behavior_trace))
    findings.extend(_audit_outcome(outcome_reference))

    run_id = (
        str(behavior_trace.get("run_id") or "")
        or str(replay_trace.get("trace_id") or "")
        or str(pack.get("audit_trace", {}).get("trace_id") or "")
        or "audit_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    )
    score = _audit_score(findings)
    verdict = "pass" if score >= 0.88 else "review" if score >= 0.62 else "fail"
    summary = _audit_summary(findings, verdict, score)
    return AuditReport.create(run_id, verdict, score, summary, findings)


def summarize_evidence_pack(report_payload: dict[str, Any] | None = None, evidence_pack: dict[str, Any] | Any | None = None) -> dict[str, Any]:
    """Build a compact extractive summary of report/evidence-pack outputs."""
    report = to_plain(report_payload or {})
    pack = to_plain(evidence_pack or {})
    runs = _runs(report, pack)
    claims = []
    entities = []
    human_review_count = 0
    for run in runs:
        entities.append(
            {
                "ticker": run.get("ticker"),
                "overall": (run.get("overall_conclusion") or {}).get("overall_label"),
                "evidence_count": len(run.get("evidence") or []),
            }
        )
        for result in run.get("atomic_claims") or []:
            human_review_count += int(bool(result.get("human_review_required")))
            claims.append(
                {
                    "claim_id": ((result.get("atomic_claim") or {}).get("claim_id")),
                    "text": ((result.get("atomic_claim") or {}).get("text")),
                    "verdict": result.get("verdict"),
                    "confidence": ((result.get("confidence_components") or {}).get("final_confidence")),
                    "human_review_required": bool(result.get("human_review_required")),
                    "review_reasons": result.get("review_reasons") or [],
                }
            )
    summary = (
        f"Checked {len(entities)} entity run(s), {len(claims)} atomic claim(s), "
        f"with {human_review_count} human-review flag(s)."
    )
    return {
        "summary": summary,
        "entities": entities,
        "claims": claims,
        "human_review_count": human_review_count,
    }


def summarize_audit_report(audit_report: dict[str, Any] | Any) -> dict[str, Any]:
    """Summarize an audit report by severity and category."""
    report = to_plain(audit_report or {})
    findings = report.get("findings") or []
    by_severity = Counter(str(item.get("severity", "info")) for item in findings)
    by_category = Counter(str(item.get("category", "unknown")) for item in findings)
    top = sorted(
        findings,
        key=lambda item: SEVERITY_RANK.get(str(item.get("severity", "info")), 0),
        reverse=True,
    )[:5]
    return {
        "summary": report.get("summary") or f"{len(findings)} audit finding(s).",
        "counts_by_severity": dict(by_severity),
        "counts_by_category": dict(by_category),
        "top_findings": top,
    }


def review_tool_surface(profile: str | None = None) -> dict[str, Any]:
    """Review tool descriptions and profile size without executing tools."""
    from .tool_profiles import tool_names_for_profile
    from .tool_registry import all_registered_tools, get_registered_tool

    names = tool_names_for_profile(profile) if profile else [tool.name for tool in all_registered_tools()]
    tools = [get_registered_tool(name) for name in names]
    findings = []
    if len(tools) > 20:
        findings.append(
            {
                "severity": "minor",
                "category": "tool_surface",
                "summary": f"Profile exposes {len(tools)} tools; prefer fewer than 20 initially.",
                "affected": profile or "all",
                "recommendation": "Move infrequent tools into retrieval_deep, audit, or review profiles.",
            }
        )
    descriptions = Counter(tool.description.strip().lower() for tool in tools)
    for text, count in descriptions.items():
        if count > 1:
            findings.append(
                {
                    "severity": "minor",
                    "category": "tool_surface",
                    "summary": "Multiple tools share the same short description.",
                    "affected": text[:80],
                    "recommendation": "Make each description encode its decision boundary.",
                }
            )
    for tool in tools:
        rich = tool.agent_description()
        missing = [
            label
            for label in ["Use when:", "Do not use when:", "Required prior state:", "Recommended next tools:"]
            if label not in rich
        ]
        if missing:
            findings.append(
                {
                    "severity": "major",
                    "category": "tool_surface",
                    "summary": f"{tool.name} is missing guidance: {', '.join(missing)}.",
                    "affected": tool.name,
                    "recommendation": "Regenerate the tool description with the standard guidance fields.",
                }
            )
        if len(rich) < 180:
            findings.append(
                {
                    "severity": "minor",
                    "category": "tool_surface",
                    "summary": f"{tool.name} description may be too terse for reliable tool choice.",
                    "affected": tool.name,
                    "recommendation": "Add clearer use/do-not-use and output semantics.",
                }
            )
    return {"findings": findings, "tool_count": len(tools), "profile": profile or "all"}


def _audit_evidence(report: dict[str, Any], pack: dict[str, Any]) -> list[AuditFinding]:
    findings = []
    for run in _runs(report, pack):
        evidence_urls = {item.get("url") for item in run.get("evidence") or [] if item.get("url")}
        fact_ids = {item.get("fact_id") for item in run.get("canonical_facts") or [] if item.get("fact_id")}
        for result in run.get("atomic_claims") or []:
            claim = result.get("atomic_claim") or {}
            claim_id = str(claim.get("claim_id") or claim.get("text") or "claim")
            verdict = str(result.get("verdict") or "")
            evidence_refs = set(result.get("evidence_urls") or [])
            fact_refs = set(result.get("canonical_fact_ids") or [])
            if verdict in {"verified", "supported", "partially_verified", "partially_supported"} and not (evidence_refs or fact_refs):
                findings.append(
                    _finding(
                        "major",
                        "evidence",
                        "Supported claim has no evidence URL or canonical fact reference.",
                        claim_id,
                        [claim_id],
                        "Require at least one evidence URL or canonical fact id before a positive verdict.",
                    )
                )
            missing_urls = sorted(ref for ref in evidence_refs if ref not in evidence_urls)
            if missing_urls:
                findings.append(
                    _finding(
                        "major",
                        "evidence",
                        "Claim references evidence URLs that are absent from the run evidence list.",
                        claim_id,
                        missing_urls[:3],
                        "Keep evidence_urls synchronized with evidence provenance.",
                    )
                )
            missing_facts = sorted(ref for ref in fact_refs if ref not in fact_ids)
            if missing_facts:
                findings.append(
                    _finding(
                        "major",
                        "evidence",
                        "Claim references canonical facts that are absent from canonical_facts.",
                        claim_id,
                        missing_facts[:3],
                        "Verify fact ids after canonicalization and before claim verification.",
                    )
                )
    return findings


def _audit_common_sense(report: dict[str, Any], pack: dict[str, Any]) -> list[AuditFinding]:
    """Review whether displayed sources are sensible for each claim."""
    findings = []
    for run in _runs(report, pack):
        evidence_by_url = {item.get("url"): item for item in run.get("evidence") or [] if item.get("url")}
        evidence_by_key = {_evidence_key(item): item for item in run.get("evidence") or []}
        facts_by_id = {item.get("fact_id"): item for item in run.get("canonical_facts") or [] if item.get("fact_id")}
        selections_by_claim = _source_selections_by_claim(run)
        for result in run.get("atomic_claims") or []:
            claim = result.get("atomic_claim") or {}
            claim_id = str(claim.get("claim_id") or claim.get("text") or "claim")
            text = str(claim.get("text") or "")
            verdict = str(result.get("verdict") or "")
            if not text or verdict == VerificationVerdict.NOT_APPLICABLE.value:
                continue

            classification = classify_argument_type(text)
            if classification.argument_type not in FACTUAL_TYPES:
                findings.append(
                    _finding(
                        "major",
                        "common_sense",
                        "Non-factual or subjective statement reached the fact-check stage.",
                        claim_id,
                        [classification.argument_type.value],
                        "Skip forecasts, opinions, reassurance/talk framing, and vague market color before retrieval.",
                    )
                )

            used_evidence = _used_evidence_for_result(result, evidence_by_url, evidence_by_key)
            used_facts = _used_facts_for_result(result, facts_by_id)
            selected_sources = selections_by_claim.get(claim_id, {}).get("selected_sources") or []
            no_displayable_source = not used_evidence and not used_facts

            if no_displayable_source and verdict in {
                VerificationVerdict.INSUFFICIENT.value,
                VerificationVerdict.NOT_FOUND.value,
                VerificationVerdict.WEAK.value,
            }:
                severity = "major" if selected_sources else "minor"
                summary = (
                    "Selected sources produced no displayable evidence for this claim."
                    if selected_sources
                    else "No displayable source was found for a fact-checkable claim."
                )
                findings.append(
                    _finding(
                        severity,
                        "coverage",
                        summary,
                        claim_id,
                        [str(item) for item in selected_sources[:4]],
                        "Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.",
                    )
                )
                continue

            for item in used_evidence:
                if not _evidence_matches_claim_common_sense(text, item, used_facts):
                    findings.append(
                        _finding(
                            "major",
                            "source_alignment",
                            "Displayed evidence appears topically unrelated to the claim.",
                            claim_id,
                            [str(item.get("url") or item.get("title") or _evidence_key(item))],
                            "Do not attach this source to the claim; rerun source selection with asset class + claim property, or mark the claim for human review.",
                        )
                    )

            if used_facts and not _facts_match_claim_common_sense(text, used_facts):
                findings.append(
                    _finding(
                        "major",
                        "source_alignment",
                        "Canonical facts used for the claim do not match the claim property.",
                        claim_id,
                        [str(item.get("fact_name") or item.get("fact_id")) for item in used_facts[:4]],
                        "Only compare facts whose metric/concept matches the property asserted by the claim.",
                    )
                )
    return findings


def _audit_computation(report: dict[str, Any], pack: dict[str, Any]) -> list[AuditFinding]:
    findings = []
    for run in _runs(report, pack):
        for result in run.get("atomic_claims") or []:
            derivation = result.get("numeric_derivation") or {}
            if not derivation:
                continue
            recomputed = _recompute_derivation(derivation)
            if recomputed is None:
                continue
            observed = _as_float(derivation.get("result"))
            if observed is None:
                continue
            tolerance = max(float(derivation.get("tolerance") or 0.000001), 0.000001)
            if abs(recomputed - observed) > tolerance:
                claim_id = (result.get("atomic_claim") or {}).get("claim_id") or "claim"
                findings.append(
                    _finding(
                        "critical",
                        "computation",
                        f"Numeric derivation result does not recompute: expected {recomputed:.6f}, got {observed:.6f}.",
                        str(claim_id),
                        [str(claim_id)],
                        "Recompute the formula from stored inputs before accepting the numeric verdict.",
                    )
                )
    return findings


def _audit_tool_use(agent_trace: dict[str, Any], report: dict[str, Any], audit_trace: dict[str, Any]) -> list[AuditFinding]:
    findings = []
    calls = agent_trace.get("tool_calls") or []
    if not calls:
        if report.get("runs") or audit_trace.get("events"):
            findings.append(
                _finding(
                    "minor",
                    "tool_use",
                    "No agent tool calls were recorded for a completed verification workflow.",
                    agent_trace.get("run_id", "agent_trace"),
                    [],
                    "Record each tool call so the chain can be independently audited.",
                )
            )
        return findings

    seen = Counter((call.get("tool_name"), _stable_args(call.get("arguments") or {})) for call in calls)
    repeated = [name for (name, _), count in seen.items() if count > 1]
    if repeated:
        findings.append(
            _finding(
                "minor",
                "tool_use",
                "Agent repeated identical tool calls.",
                ", ".join(sorted(set(repeated))),
                sorted(set(repeated))[:5],
                "Cache or reuse prior tool outputs when arguments are unchanged.",
            )
        )

    errors = [call for call in calls if call.get("status") == "error"]
    if errors:
        findings.append(
            _finding(
                "major",
                "tool_use",
                f"{len(errors)} tool call(s) failed during the agent run.",
                agent_trace.get("run_id", "agent_trace"),
                [str(call.get("call_id")) for call in errors[:5]],
                "Stop after repeated errors or switch to a fallback path with an explicit note.",
            )
        )

    names = [str(call.get("tool_name")) for call in calls]
    if _first_index(names, "verify_atomic_claim") < _first_index(names, "retrieve_evidence"):
        findings.append(
            _finding(
                "major",
                "tool_use",
                "verify_atomic_claim appears before retrieve_evidence in the agent trace.",
                agent_trace.get("run_id", "agent_trace"),
                ["verify_atomic_claim", "retrieve_evidence"],
                "Retrieve and normalize evidence before claim-level verification.",
            )
        )
    if report.get("runs") and "retrieve_evidence" not in names and "build_evidence_pack" not in names:
        findings.append(
            _finding(
                "major",
                "tool_use",
                "Completed report has no recorded retrieval or end-to-end evidence-pack tool call.",
                agent_trace.get("run_id", "agent_trace"),
                names[:5],
                "Ensure retrieval or build_evidence_pack is present in every fact-checking trace.",
            )
        )
    return findings


def _audit_constraints(report: dict[str, Any], pack: dict[str, Any]) -> list[AuditFinding]:
    findings = []
    for run in _runs(report, pack):
        for result in run.get("atomic_claims") or []:
            components = result.get("confidence_components") or {}
            confidence = _as_float(components.get("final_confidence"))
            if confidence is not None and confidence < 0.55 and not result.get("human_review_required"):
                claim_id = (result.get("atomic_claim") or {}).get("claim_id") or "claim"
                findings.append(
                    _finding(
                        "major",
                        "constraint",
                        "Low-confidence claim is not marked for human review.",
                        str(claim_id),
                        [str(claim_id)],
                        "Trigger human_review_required for low confidence or explain why the guardrail is bypassed.",
                    )
                )
        selections = (run.get("metadata") or {}).get("source_selection") or []
        for selection in selections:
            selected = selection.get("selected_sources") or []
            claim_id = str(selection.get("claim_id") or "claim")
            if selected and not any(
                str(source).startswith("sec_")
                or source in {"fred", "treasury_fiscal_data", "gleif_entity", "world_bank_indicators"}
                for source in selected
            ):
                findings.append(
                    _finding(
                        "minor",
                        "constraint",
                        "Source selection lacks an obvious official primary source.",
                        claim_id,
                        selected[:4],
                        "Prefer official primary sources for factual verification or require human review.",
                    )
                )
    markdown = str(report.get("report_markdown") or "")
    if "investment advice" in markdown.lower() and "not" not in markdown.lower():
        findings.append(
            _finding(
                "major",
                "constraint",
                "Report may imply investment advice without a clear non-advice disclaimer.",
                "report_markdown",
                [],
                "State that the system verifies claims against evidence and does not provide investment advice.",
            )
        )
    return findings


def _audit_reasoning(report: dict[str, Any], pack: dict[str, Any], config=None) -> list[AuditFinding]:
    findings = []
    for run in _runs(report, pack):
        evidence = run.get("evidence") or []
        has_official = any(item.get("is_official_primary") for item in evidence)
        for result in run.get("atomic_claims") or []:
            claim = result.get("atomic_claim") or {}
            text = str(claim.get("text") or "")
            verdict = str(result.get("verdict") or "")
            if _looks_causal(text) and verdict in {"supported", "verified"} and not has_official:
                findings.append(
                    _finding(
                        "major",
                        "reasoning",
                        "Causal/explanatory claim is supported without official or strong textual evidence.",
                        str(claim.get("claim_id") or text[:80]),
                        [str(claim.get("claim_id") or "")],
                        "Use a narrow reasoning judge and require textual evidence for causal language.",
                    )
                )
            if _has_llm_config(config) and evidence and verdict in {"supported", "verified", "partially_verified", "partially_supported"}:
                check = create_judge(config).judge_logic_claim(
                    text,
                    [_evidence_from_plain(item) for item in evidence[:4]],
                    ArgumentType.ATTRIBUTION_FACT if _looks_causal(text) else ArgumentType.METRIC_FACT,
                )
                if check.verdict in {VerificationVerdict.WEAK.value, VerificationVerdict.INSUFFICIENT.value, VerificationVerdict.NOT_FOUND.value}:
                    findings.append(
                        _finding(
                            "major",
                            "reasoning",
                            "Narrow reasoning judge does not support the positive verdict.",
                            str(claim.get("claim_id") or text[:80]),
                            check.evidence_urls[:3],
                            "Downgrade the verdict or add stronger evidence before publishing the report.",
                        )
                    )
    return findings


def _audit_prompt(agent_trace: dict[str, Any]) -> list[AuditFinding]:
    if not agent_trace:
        return []
    findings = []
    if not agent_trace.get("instructions_hash"):
        findings.append(
            _finding(
                "minor",
                "prompt",
                "Agent trace is missing an instructions hash.",
                str(agent_trace.get("run_id") or "agent_trace"),
                [],
                "Record a stable hash for the system instructions so prompt changes are reviewable.",
            )
        )
    if agent_trace.get("provider") not in {None, "", "none"} and not agent_trace.get("model"):
        findings.append(
            _finding(
                "minor",
                "prompt",
                "Agent trace records a provider but not a model id.",
                str(agent_trace.get("run_id") or "agent_trace"),
                [],
                "Store the model id with each run to make prompt and tool-use reviews reproducible.",
            )
        )
    return findings


def _audit_tool_surface_trace(agent_trace: dict[str, Any]) -> list[AuditFinding]:
    profile = str(agent_trace.get("tool_profile") or "")
    if not profile:
        return []
    if profile == "all":
        return [
            _finding(
                "minor",
                "tool_surface",
                "Agent run used the all-tools profile.",
                str(agent_trace.get("run_id") or "agent_trace"),
                [profile],
                "Use a narrower profile such as agent_core, retrieval_deep, audit, or review.",
            )
        ]
    return []


def _audit_outcome(outcome_reference: dict[str, Any] | None) -> list[AuditFinding]:
    if not outcome_reference:
        return []
    return [
        _finding(
            "info",
            "outcome",
            "Outcome reference supplied; treat it as a low-weight retrospective annotation.",
            str(outcome_reference.get("id") or "outcome_reference"),
            [],
            "Do not override evidence-based verdicts solely because realized outcomes are noisy.",
        )
    ]


def _runs(report: dict[str, Any], pack: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("runs"):
        return list(report.get("runs") or [])
    if pack:
        return [pack]
    return []


def _source_selections_by_claim(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for selection in (run.get("metadata") or {}).get("source_selection") or []:
        claim_id = str(selection.get("claim_id") or "")
        if claim_id:
            rows[claim_id] = selection
    return rows


def _used_evidence_for_result(
    result: dict[str, Any],
    evidence_by_url: dict[str, dict[str, Any]],
    evidence_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    for key in result.get("evidence_keys") or []:
        item = evidence_by_key.get(key)
        if item:
            items.append(item)
    for url in result.get("evidence_urls") or []:
        item = evidence_by_url.get(url)
        if item:
            items.append(item)
    return _dedupe_plain_sources(items)


def _used_facts_for_result(result: dict[str, Any], facts_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [facts_by_id[item] for item in result.get("canonical_fact_ids") or [] if item in facts_by_id]


def _dedupe_plain_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        key = item.get("url") or _evidence_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _evidence_key(item: dict[str, Any]) -> str:
    return f"{item.get('source_tier') or ''}:{item.get('domain') or ''}:{item.get('published_at') or 'undated'}"


def _evidence_matches_claim_common_sense(
    claim: str,
    evidence: dict[str, Any],
    facts: list[dict[str, Any]],
) -> bool:
    text = " ".join(str(evidence.get(field) or "") for field in ["title", "text", "snippet", "domain", "url"])
    if _is_price_evidence(text) and needs_historical_price_data(claim):
        return True
    if _metric_intents(claim) & _metric_intents(text):
        return True
    if facts and _facts_match_claim_common_sense(claim, facts):
        return True
    return _token_overlap_score(claim, text) >= 0.18


def _facts_match_claim_common_sense(claim: str, facts: list[dict[str, Any]]) -> bool:
    fact_text = " ".join(" ".join(str(item.get(field) or "") for field in ["fact_name", "unit", "currency"]) for item in facts)
    if _metric_intents(claim) & _metric_intents(fact_text):
        return True
    return _token_overlap_score(claim, fact_text) >= 0.18


def _is_price_evidence(text: str) -> bool:
    lower = text.lower()
    return "historical prices" in lower or "historical daily close prices" in lower or "latest_daily_return_pct" in lower


def _metric_intents(text: str) -> set[str]:
    lower = _split_camel(str(text)).lower()
    intents: set[str] = set()
    patterns = {
        "revenue": r"\b(revenue|revenues|sales)\b",
        "eps": r"\b(eps|earnings per share|earningspershare|basic eps|diluted eps)\b",
        "income": r"\b(net income|operating income|income)\b",
        "cash_flow": r"\b(cash flow|operating cash|free cash flow|capex)\b",
        "assets": r"\b(assets?|liabilities)\b",
        "debt": r"\b(debt|borrowings|leverage)\b",
        "margin": r"\b(margin|gross profit)\b",
        "supply": r"\b(supply|supplies|inventory|stockpiles|backlog)\b",
        "market_size": r"\b(addressable market|market size|market opportunity|tam)\b",
        "price": r"\b(price|prices|return|returns|shares?|stock|closing high|record high)\b",
        "rates": r"\b(rate|rates|yield|yields|sofr|treasury|fed funds)\b",
        "inflation": r"\b(cpi|ppi|pce|inflation|hicp)\b",
        "labor": r"\b(payrolls?|jobs?|unemployment|wages?|jolts)\b",
        "fx": r"\b(fx|forex|dollar|yen|euro|sterling|exchange rate)\b",
        "commodity": r"\b(wti|brent|crude oil|gold|natural gas|gasoline|copper)\b",
        "credit": r"\b(oas|spread|spreads|high yield|investment grade|corporate bond)\b",
        "positioning": r"\b(open interest|positioning|managed money|cot|futures positions?)\b",
    }
    for intent, pattern in patterns.items():
        if re.search(pattern, lower):
            intents.add(intent)
    return intents


def _token_overlap_score(left: str, right: str) -> float:
    left_tokens = _common_sense_tokens(left)
    right_tokens = _common_sense_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _common_sense_tokens(text: str) -> set[str]:
    normalized = _split_camel(str(text)).lower().replace("-", " ")
    aliases = {
        "revenues": "revenue",
        "sales": "revenue",
        "shares": "share",
        "stocks": "stock",
        "processors": "processor",
        "cpus": "cpu",
    }
    return {
        aliases.get(token, token)
        for token in re.findall(r"[a-z][a-z0-9]+", normalized)
        if len(token) > 2 and token not in _COMMON_SENSE_STOPWORDS
    }


def _split_camel(text: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)


_COMMON_SENSE_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "apr",
    "april",
    "basic",
    "before",
    "billion",
    "claim",
    "company",
    "data",
    "displayable",
    "during",
    "ended",
    "ending",
    "evidence",
    "fact",
    "facts",
    "filing",
    "first",
    "fiscal",
    "for",
    "form",
    "from",
    "has",
    "inc",
    "into",
    "latest",
    "million",
    "new",
    "previous",
    "quarter",
    "reported",
    "said",
    "says",
    "sec",
    "source",
    "the",
    "this",
    "undated",
    "usd",
    "was",
    "were",
    "with",
    "year",
}


def _recompute_derivation(derivation: dict[str, Any]) -> float | None:
    expression = str(derivation.get("expression") or "")
    inputs = derivation.get("inputs") or {}
    if expression == "(current - prior) / abs(prior)":
        current = _as_float(inputs.get("current"))
        prior = _as_float(inputs.get("prior"))
        if current is None or prior in {None, 0}:
            return None
        return round((current - prior) / abs(prior), 6)
    if "/" in expression:
        numerator = _as_float(inputs.get("numerator"))
        denominator = _as_float(inputs.get("denominator"))
        if numerator is None or denominator in {None, 0}:
            return None
        return round(numerator / denominator, 6)
    if "NetCashProvided" in expression:
        ocf = _as_float(inputs.get("operating_cash_flow"))
        capex = _as_float(inputs.get("capital_expenditures"))
        if ocf is None or capex is None:
            return None
        return round(ocf - abs(capex), 6)
    return None


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_index(values: list[str], target: str) -> int:
    try:
        return values.index(target)
    except ValueError:
        return 10**9


def _stable_args(args: dict[str, Any]) -> str:
    import json

    return json.dumps(args, sort_keys=True, ensure_ascii=True, default=str)


def _looks_causal(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in ["because", "due to", "driven by", "primarily from", "caused by"])


def _has_llm_config(config: Any) -> bool:
    if config is None:
        return False
    return bool(
        (getattr(config, "openai_api_key", None) and getattr(config, "openai_model", None))
        or (getattr(config, "anthropic_api_key", None) and getattr(config, "anthropic_model", None))
    )


def _evidence_from_plain(item: dict[str, Any]) -> Evidence:
    source = assess_source(str(item.get("url", "")), str(item.get("title", "")))
    return Evidence(
        url=str(item.get("url", "")),
        title=str(item.get("title", "")),
        text=str(item.get("text") or item.get("snippet") or ""),
        source_type=_enum_value(SourceType, item.get("source_type"), source.source_type),
        source_tier=_enum_value(SourceTier, item.get("source_tier"), source.source_tier),
        domain=str(item.get("domain") or source.domain),
        published_at=item.get("published_at"),
        license_tag=_enum_value(LicenseTag, item.get("license_tag"), source.license_tag),
        is_official_primary=bool(item.get("is_official_primary", source.is_official_primary)),
        source_authority=float(item.get("source_authority", source.authority_score)),
        recency_score=float(item.get("recency_score", 0.0)),
        relevance_score=float(item.get("relevance_score", 0.0)),
        entity_match_score=float(item.get("entity_match_score", 0.0)),
        numeric_consistency_score=float(item.get("numeric_consistency_score", 0.0)),
        support_label=_enum_value(SupportLabel, item.get("support_label"), SupportLabel.NOT_ENOUGH_INFO),
        support_score=float(item.get("support_score", 0.0)),
        reasoning_quality_score=float(item.get("reasoning_quality_score", 0.0)),
        independence_score=float(item.get("independence_score", 0.0)),
        notes=[str(note) for note in item.get("notes", [])],
    )


def _enum_value(enum_cls, value: Any, default):
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _audit_score(findings: list[AuditFinding]) -> float:
    penalty = 0.0
    for finding in findings:
        penalty += {"info": 0.01, "minor": 0.04, "major": 0.14, "critical": 0.35}.get(finding.severity, 0.04)
    return round(max(0.0, 1.0 - penalty), 3)


def _audit_summary(findings: list[AuditFinding], verdict: str, score: float) -> str:
    if not findings:
        return f"Audit {verdict}: no findings; score {score:.2f}."
    counts = Counter(finding.severity for finding in findings)
    parts = ", ".join(f"{severity}={counts[severity]}" for severity in ["critical", "major", "minor", "info"] if counts[severity])
    return f"Audit {verdict}: {len(findings)} finding(s) ({parts}); score {score:.2f}."


def _finding(
    severity: str,
    category: str,
    summary: str,
    affected: str,
    trace_refs: list[str],
    recommendation: str,
) -> AuditFinding:
    return AuditFinding(
        severity=severity,
        category=category,
        summary=summary,
        affected=affected,
        trace_refs=trace_refs,
        recommendation=recommendation,
    )
