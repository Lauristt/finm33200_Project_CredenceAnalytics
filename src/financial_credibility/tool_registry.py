"""Agent-facing registry for high-level and atomic credibility tools.

The registry is intentionally declarative. It describes what each tool does and
how an LLM agent should call it, while `tool_runtime.py` owns execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ToolSpec


@dataclass(frozen=True)
class RegisteredTool:
    """Human-readable and machine-readable metadata for one callable tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    when_to_use: str
    data_sources: list[str] = field(default_factory=list)
    requires_keys: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
        )

    def to_doc_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "when_to_use": self.when_to_use,
            "data_sources": self.data_sources,
            "requires_keys": self.requires_keys,
            "limitations": self.limitations,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


def all_registered_tools() -> list[RegisteredTool]:
    """Return all tools exposed to an agent."""
    return [
        _classify_claim_tool(),
        _extract_entities_tool(),
        _decompose_claims_tool(),
        _resolve_entity_tool(),
        _route_sources_tool(),
        _select_sources_tool(),
        _get_sec_company_facts_tool(),
        _get_recent_filings_tool(),
        _get_canonical_facts_tool(),
        _get_company_fundamentals_tool(),
        _get_historical_prices_tool(),
        _compare_stock_performance_tool(),
        _retrieve_evidence_tool(),
        _verify_atomic_claim_tool(),
        _calibrate_uncertainty_tool(),
        _build_audit_trace_tool(),
        _verify_numeric_claim_tool(),
        _verify_logic_claim_tool(),
        _verify_source_quality_tool(),
        _aggregate_credibility_tool(),
        _build_evidence_pack_tool(),
    ]


def get_registered_tool(name: str) -> RegisteredTool:
    """Look up a registered tool by name."""
    for tool in all_registered_tools():
        if tool.name == name:
            return tool
    raise KeyError(f"Unknown tool: {name}")


def all_tool_specs() -> list[ToolSpec]:
    """Return provider-neutral tool specs for all registered tools."""
    return [tool.to_tool_spec() for tool in all_registered_tools()]


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _search_result_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object"}}


def _evidence_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object"}}


def _classify_claim_tool() -> RegisteredTool:
    return RegisteredTool(
        name="classify_claim",
        description="Classify a financial claim into a rubric argument type.",
        when_to_use="Use first when the agent needs to decide whether a claim is factual, opinion/analysis, attribution, event-based, or forecast-like.",
        data_sources=[],
        requires_keys=[],
        limitations=["Rule-based classifier; useful for routing, not final truth assessment."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string", "description": "Financial claim to classify."},
            },
            ["claim"],
        ),
        output_schema=_object_schema(
            {
                "argument_type": {"type": "string"},
                "confidence": {"type": "number"},
                "signals": {"type": "array", "items": {"type": "string"}},
                "needs_decomposition": {"type": "boolean"},
            }
        ),
    )


def _extract_entities_tool() -> RegisteredTool:
    return RegisteredTool(
        name="extract_entities",
        description="Extract public companies, issuers, securities, and ticker hints from an investment memo.",
        when_to_use="Use before claim decomposition when the user provides a memo but no ticker/entity hints.",
        data_sources=["Optional OpenAI/Anthropic entity extractor", "Local ticker/name heuristics"],
        requires_keys=["Optional OPENAI_API_KEY/OPENAI_MODEL or ANTHROPIC_API_KEY/ANTHROPIC_MODEL"],
        limitations=[
            "The tool returns only entities explicitly mentioned in the memo.",
            "Entities without confident public tickers are reported as unresolved and are not used for SEC ticker-based retrieval.",
        ],
        input_schema=_object_schema(
            {
                "memo": {"type": "string"},
                "max_entities": {"type": "integer", "default": 8},
            },
            ["memo"],
        ),
        output_schema={"type": "object"},
    )


def _decompose_claims_tool() -> RegisteredTool:
    return RegisteredTool(
        name="decompose_claims",
        description="Split a longer financial statement into atomic verifiable claims.",
        when_to_use="Use before retrieval when a memo, paragraph, or multi-part sentence contains more than one financial claim.",
        data_sources=[],
        requires_keys=[],
        limitations=["Rule-based decomposition; callers can override by passing one atomic claim at a time."],
        input_schema=_object_schema({"claim": {"type": "string"}}, ["claim"]),
        output_schema=_object_schema({"claims": {"type": "array", "items": {"type": "object"}}}),
    )


def _resolve_entity_tool() -> RegisteredTool:
    return RegisteredTool(
        name="resolve_entity",
        description="Resolve ticker/CIK/LEI identifiers into a single entity mapping.",
        when_to_use="Use before official retrieval or claim verification to record entity confidence and mapping issues.",
        data_sources=["SEC metadata when provided", "GLEIF/LEI identifiers when provided"],
        requires_keys=[],
        limitations=["MVP resolver uses available identifiers and evidence metadata; it does not perform live GLEIF search by company name."],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "cik": {"type": "string"},
                "lei": {"type": "string"},
                "figi": {"type": "string"},
                "evidence": _evidence_array(),
                "search_results": _search_result_array(),
            },
            ["ticker"],
        ),
        output_schema={"type": "object"},
    )


def _route_sources_tool() -> RegisteredTool:
    return RegisteredTool(
        name="route_sources",
        description="Choose official source adapters for a claim.",
        when_to_use="Use after claim decomposition to decide whether to call SEC, FRED, Treasury, GLEIF, or supplemental sources.",
        data_sources=[],
        requires_keys=[],
        limitations=["Keyword route planner; the retrieval layer still determines which sources are actually available."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "official_only": {"type": "boolean", "default": True},
            },
            ["claim"],
        ),
        output_schema={"type": "object"},
    )


def _select_sources_tool() -> RegisteredTool:
    return RegisteredTool(
        name="select_sources",
        description="Select source candidates with brief-first progressive disclosure, optional LLM refinement, and policy validation.",
        when_to_use="Use after claim decomposition when the agent needs to choose which official or supplemental data sources to call.",
        data_sources=["Source catalog", "Local source description files", "Optional OpenAI/Anthropic source selector"],
        requires_keys=["Optional OPENAI_API_KEY/OPENAI_MODEL or ANTHROPIC_API_KEY/ANTHROPIC_MODEL"],
        limitations=[
            "The LLM can only choose from provided catalog candidates.",
            "Detailed source descriptions are only loaded for selected first-pass candidates.",
            "Policy validation may add official primary sources or discard unknown ids.",
        ],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "candidate_limit": {"type": "integer", "default": 6},
                "max_selected": {"type": "integer", "default": 4},
                "include_planned_sources": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include official/planned source descriptions even when no runtime adapter exists yet.",
                },
            },
            ["claim"],
        ),
        output_schema=_object_schema(
            {
                "selections": {"type": "array", "items": {"type": "object"}},
            }
        ),
    )


def _get_sec_company_facts_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_sec_company_facts",
        description="Retrieve SEC XBRL company facts relevant to a claim.",
        when_to_use="Use for official numeric fundamentals such as revenue, net income, EPS, assets, debt, margins, or cash flow.",
        data_sources=["SEC EDGAR company facts"],
        requires_keys=[],
        limitations=["Concept selection is keyword-based, not a full XBRL semantic planner."],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "claim": {"type": "string", "description": "Claim text used to select SEC concepts."},
            },
            ["ticker", "claim"],
        ),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _get_recent_filings_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_recent_filings",
        description="Retrieve recent SEC 10-K, 10-Q, and 8-K filings for a ticker.",
        when_to_use="Use when the agent needs official recent filing context or links.",
        data_sources=["SEC EDGAR submissions"],
        requires_keys=[],
        limitations=["Returns filing metadata/snippets, not full filing text unless live extraction is enabled elsewhere."],
        input_schema=_object_schema({"ticker": {"type": "string"}}, ["ticker"]),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _get_canonical_facts_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_canonical_facts",
        description="Normalize structured search results or official evidence into canonical facts.",
        when_to_use="Use after SEC/FRED/Treasury/GLEIF retrieval, before claim-level numeric or evidence verification.",
        data_sources=["SEC company facts", "FRED observations", "Official evidence objects"],
        requires_keys=[],
        limitations=["MVP canonicalization parses compact provider snippets and official evidence metadata, not full iXBRL documents."],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "search_results": _search_result_array(),
                "evidence": _evidence_array(),
                "cik": {"type": "string"},
                "lei": {"type": "string"},
            },
            ["ticker"],
        ),
        output_schema=_object_schema(
            {
                "entity_resolution": {"type": "object"},
                "canonical_facts": {"type": "array", "items": {"type": "object"}},
            }
        ),
    )


def _get_company_fundamentals_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_company_fundamentals",
        description="Retrieve company profile, income statement, earnings, and basic metric snippets.",
        when_to_use="Use for broad operating/financial performance questions before judging whether a company performed well or poorly.",
        data_sources=["Alpha Vantage", "Finnhub", "Financial Modeling Prep"],
        requires_keys=["ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "FMP_API_KEY"],
        limitations=["Returns compact provider snippets; not a complete financial statement model."],
        input_schema=_object_schema({"ticker": {"type": "string"}}, ["ticker"]),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _get_historical_prices_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_historical_prices",
        description="Retrieve and summarize daily historical stock prices.",
        when_to_use="Use for claims about stock price performance, volatility, oscillation, trend, drawdown, range-bound behavior, or a date-window return.",
        data_sources=["Alpha Vantage", "Financial Modeling Prep", "Finnhub", "Stooq fallback"],
        requires_keys=["One of ALPHA_VANTAGE_API_KEY, FMP_API_KEY, FINNHUB_API_KEY; Stooq fallback may require no key when available"],
        limitations=["Does not automatically include dividends unless the provider's close series is adjusted; benchmark comparison needs compare_stock_performance."],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            ["ticker", "start_date", "end_date"],
        ),
        output_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "provider": {"type": "string"},
                "summary": {"type": "object"},
                "evidence_text": {"type": "string"},
                "evidence_url": {"type": "string"},
            }
        ),
    )


def _compare_stock_performance_tool() -> RegisteredTool:
    return RegisteredTool(
        name="compare_stock_performance",
        description="Compare a ticker's historical price return against a benchmark.",
        when_to_use="Use for relative performance claims such as underperformed, outperformed, lagged the market, or beat the Nasdaq/S&P 500.",
        data_sources=["Alpha Vantage", "Financial Modeling Prep", "Finnhub", "Stooq fallback"],
        requires_keys=["Same as get_historical_prices"],
        limitations=["Price-return comparison only; dividends and total-return indices may not be included."],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "benchmark_ticker": {"type": "string", "default": "SPY"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            ["ticker", "benchmark_ticker", "start_date", "end_date"],
        ),
        output_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "benchmark_ticker": {"type": "string"},
                "ticker_return_pct": {"type": "number"},
                "benchmark_return_pct": {"type": "number"},
                "relative_return_pct": {"type": "number"},
                "summary": {"type": "string"},
            }
        ),
    )


def _retrieve_evidence_tool() -> RegisteredTool:
    return RegisteredTool(
        name="retrieve_evidence",
        description="Retrieve and normalize evidence for a claim without final verification.",
        when_to_use="Use when the agent wants evidence objects first, then plans to call verification tools separately.",
        data_sources=["Configured structured sources", "Optional Serper", "Optional Jina Reader"],
        requires_keys=["Optional provider keys depending on configured sources"],
        limitations=["Does not run LLM semantic verification by itself."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "ticker": {"type": "string"},
                "as_of_date": {"type": "string"},
                "max_sources": {"type": "integer", "default": 8},
                "prefetched_results": _search_result_array(),
            },
            ["claim", "ticker"],
        ),
        output_schema=_object_schema(
            {
                "argument_type": {"type": "string"},
                "evidence": _evidence_array(),
                "search_notes": {"type": "array"},
                "extraction_notes": {"type": "array"},
            }
        ),
    )


def _verify_atomic_claim_tool() -> RegisteredTool:
    return RegisteredTool(
        name="verify_atomic_claim",
        description="Verify one or more atomic claims with evidence, canonical facts, uncertainty, and HITL flags.",
        when_to_use="Use when the agent wants claim-level verdicts rather than only a whole-paragraph evidence pack.",
        data_sources=["Provided evidence", "Provided canonical facts", "OpenAI/Anthropic judge when configured"],
        requires_keys=["Optional OPENAI_API_KEY or ANTHROPIC_API_KEY"],
        limitations=["Uses the same narrow judges and heuristic numeric derivations as the main toolkit."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "ticker": {"type": "string"},
                "evidence": _evidence_array(),
                "canonical_facts": {"type": "array", "items": {"type": "object"}},
                "cik": {"type": "string"},
                "lei": {"type": "string"},
            },
            ["claim", "ticker", "evidence"],
        ),
        output_schema=_object_schema({"atomic_claims": {"type": "array", "items": {"type": "object"}}}),
    )


def _calibrate_uncertainty_tool() -> RegisteredTool:
    return RegisteredTool(
        name="calibrate_uncertainty",
        description="Return confidence components and human-review triggers for claim-level verification.",
        when_to_use="Use after evidence and canonical facts are available to decide whether automatic verdicts need human review.",
        data_sources=["Provided evidence", "Provided canonical facts"],
        requires_keys=["Optional OpenAI/Anthropic key if semantic logic fallback is needed"],
        limitations=["Runs the same calibrator as verify_atomic_claim and returns claim-level results."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "ticker": {"type": "string"},
                "evidence": _evidence_array(),
                "canonical_facts": {"type": "array", "items": {"type": "object"}},
            },
            ["claim", "ticker", "evidence"],
        ),
        output_schema=_object_schema({"atomic_claims": {"type": "array", "items": {"type": "object"}}}),
    )


def _build_audit_trace_tool() -> RegisteredTool:
    return RegisteredTool(
        name="build_audit_trace",
        description="Build a replayable audit trace for a claim verification task.",
        when_to_use="Use at the end of a manual atomic workflow to preserve inputs, evidence, facts, verdicts, and review reasons.",
        data_sources=["Provided workflow objects"],
        requires_keys=[],
        limitations=["The high-level build_evidence_pack tool automatically includes an audit_trace."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "ticker": {"type": "string"},
                "as_of_date": {"type": "string"},
                "search_results": _search_result_array(),
                "evidence": _evidence_array(),
                "canonical_facts": {"type": "array", "items": {"type": "object"}},
            },
            ["claim", "ticker"],
        ),
        output_schema={"type": "object"},
    )


def _verify_numeric_claim_tool() -> RegisteredTool:
    return RegisteredTool(
        name="verify_numeric_claim",
        description="Verify numbers, periods, and units in a claim against evidence.",
        when_to_use="Use after retrieving evidence for claims with explicit numbers such as revenue, EPS, margins, returns, or dates.",
        data_sources=["Provided evidence"],
        requires_keys=["Optional OpenAI/Anthropic key for fallback when fuzzy matching cannot decide"],
        limitations=["Temporal lookback durations such as 10 months are ignored as non-substantive numeric facts."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "evidence": _evidence_array(),
            },
            ["claim", "evidence"],
        ),
        output_schema={"type": "object"},
    )


def _verify_logic_claim_tool() -> RegisteredTool:
    return RegisteredTool(
        name="verify_logic_claim",
        description="Verify whether a claim's reasoning or inference is supported by evidence.",
        when_to_use="Use for semantic judgments such as performed poorly, stock seems oscillating, underperformed, strong earnings, or valuation commentary.",
        data_sources=["Provided evidence", "OpenAI or Anthropic judge when configured"],
        requires_keys=["Optional OPENAI_API_KEY or ANTHROPIC_API_KEY"],
        limitations=["The result depends on evidence quality and the configured narrow LLM judge."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "evidence": _evidence_array(),
                "argument_type": {"type": "string"},
            },
            ["claim", "evidence"],
        ),
        output_schema={"type": "object"},
    )


def _verify_source_quality_tool() -> RegisteredTool:
    return RegisteredTool(
        name="verify_source_quality",
        description="Assess whether evidence sources are authoritative, recent, and independent enough.",
        when_to_use="Use when the agent has gathered evidence and needs a source-confidence dimension before final judgment.",
        data_sources=["Provided evidence"],
        requires_keys=[],
        limitations=["Depends on source metadata and heuristic independence scoring."],
        input_schema=_object_schema(
            {
                "evidence": _evidence_array(),
                "argument_type": {"type": "string"},
            },
            ["evidence"],
        ),
        output_schema={"type": "object"},
    )


def _aggregate_credibility_tool() -> RegisteredTool:
    return RegisteredTool(
        name="aggregate_credibility",
        description="Aggregate evidence-level scores into deterministic score, verdict, and label.",
        when_to_use="Use after evidence has been retrieved and optionally judged, when a deterministic rubric score is needed.",
        data_sources=["Provided evidence"],
        requires_keys=[],
        limitations=["This is a glass-box score; for final user-facing confidence prefer numeric/logic/source checks plus overall conclusion."],
        input_schema=_object_schema(
            {
                "evidence": _evidence_array(),
                "argument_type": {"type": "string"},
                "risk_flags": {"type": "array", "items": {"type": "string"}},
            },
            ["evidence"],
        ),
        output_schema={"type": "object"},
    )


def _build_evidence_pack_tool() -> RegisteredTool:
    return RegisteredTool(
        name="build_evidence_pack",
        description="Run the end-to-end credibility pipeline for a US equity financial claim.",
        when_to_use="Use for one-shot credibility checks when the agent does not need to manually plan lower-level retrieval and verification calls.",
        data_sources=["All configured retrieval sources", "OpenAI/Anthropic judge when configured"],
        requires_keys=["Optional provider keys; optional OPENAI_API_KEY or ANTHROPIC_API_KEY"],
        limitations=["Less flexible than atomic tools for vague multi-part claims; agents can decompose manually when needed."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "ticker": {"type": "string"},
                "as_of_date": {"type": "string"},
                "max_sources": {"type": "integer", "default": 8},
                "mode": {"type": "string", "enum": ["strict", "agentic"], "default": "agentic"},
                "prefetched_results": _search_result_array(),
            },
            ["claim", "ticker"],
        ),
        output_schema={"type": "object"},
    )
