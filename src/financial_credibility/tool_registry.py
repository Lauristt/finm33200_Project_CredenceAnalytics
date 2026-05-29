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
            description=self.agent_description(),
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
            "agent_description": self.agent_description(),
        }

    def agent_description(self) -> str:
        """Return a decision-oriented description for LLM tool choice."""
        key_notes = "; ".join(self.requires_keys) if self.requires_keys else "No API key required beyond the runtime config."
        limitations = "; ".join(self.limitations) if self.limitations else "No special limitations beyond the input schema."
        next_tools = _recommended_next_tools(self.name)
        prior_state = _required_prior_state(self.name)
        return " ".join(
            [
                f"Purpose: {self.description}",
                f"Use when: {self.when_to_use}",
                f"Do not use when: {_do_not_use_when(self.name)}",
                f"Required prior state: {prior_state}",
                f"Output means: {_output_means(self.name)}",
                f"Recommended next tools: {next_tools}",
                f"Key/cost notes: {key_notes}",
                f"Common failure modes: {limitations}",
            ]
        )


def all_registered_tools() -> list[RegisteredTool]:
    """Return all tools exposed to an agent."""
    return [
        _preprocess_statement_tool(),
        _classify_claim_tool(),
        _extract_entities_tool(),
        _map_asset_sources_tool(),
        _load_source_documentation_tool(),
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
        _get_income_statement_tool(),
        _get_balance_sheet_tool(),
        _get_cash_flow_statement_tool(),
        _get_earnings_history_tool(),
        _retrieve_evidence_tool(),
        _verify_atomic_claim_tool(),
        _calibrate_uncertainty_tool(),
        _build_audit_trace_tool(),
        _verify_numeric_claim_tool(),
        _verify_logic_claim_tool(),
        _verify_source_quality_tool(),
        _aggregate_credibility_tool(),
        _build_evidence_pack_tool(),
        _audit_verification_chain_tool(),
        _summarize_evidence_pack_tool(),
        _summarize_audit_report_tool(),
        _review_tool_surface_tool(),
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
        when_to_use="Use first when the agent needs to decide whether a statement is an objective, falsifiable asset/issuer/security/macro claim. Treat investor reassurance, management communication purpose, talk/discussion framing, and vague beat/priced-in/quarter-after-quarter commentary as opinion unless it gives concrete metric, period, value, and baseline.",
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


def _preprocess_statement_tool() -> RegisteredTool:
    return RegisteredTool(
        name="preprocess_statement",
        description="Clean copied webpage/article text before entity extraction, claim decomposition, and retrieval.",
        when_to_use="Use first when the user pasted a full webpage, article, transcript, or financial statement that may include ads, nav text, cookie prompts, sponsored blocks, duplicate lines, or unrelated boilerplate.",
        data_sources=[],
        requires_keys=[],
        limitations=[
            "Rule-based cleaner; it is conservative and may leave some benign boilerplate in place.",
            "It should not be used to summarize or rewrite the factual content of a claim.",
        ],
        input_schema=_object_schema(
            {
                "statement": {"type": "string"},
            },
            ["statement"],
        ),
        output_schema=_object_schema(
            {
                "cleaned_statement": {"type": "string"},
                "changed": {"type": "boolean"},
                "removed_line_count": {"type": "integer"},
                "removed_examples": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
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
        when_to_use="Use before retrieval when a memo, paragraph, or multi-part sentence contains more than one objective, falsifiable asset claim; skip forecasts, opinions, investor reassurance, management communication purpose, discussion/talk framing, and vague non-falsifiable market color.",
        data_sources=[],
        requires_keys=[],
        limitations=["Rule-based decomposition; callers can override by passing one atomic claim at a time."],
        input_schema=_object_schema({"claim": {"type": "string"}}, ["claim"]),
        output_schema=_object_schema({"claims": {"type": "array", "items": {"type": "object"}}}),
    )


def _map_asset_sources_tool() -> RegisteredTool:
    return RegisteredTool(
        name="map_asset_sources",
        description="Map extracted entities and asset classes to candidate data sources, concrete series IDs, endpoints, and adapter status.",
        when_to_use="Use after entity extraction and before source selection when a claim mentions macro, rates, FX, commodities, credit, fixed income, derivatives, indexes, ETFs, or non-US-equity assets.",
        data_sources=["Structured asset-source coverage map", "Source catalog route planner"],
        requires_keys=[],
        limitations=[
            "This is a planning map; it does not call external APIs.",
            "Planned or entitlement-limited sources may appear so the agent can surface coverage gaps.",
        ],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "entities": {"type": "array", "items": {"type": "object"}},
                "include_planned_sources": {"type": "boolean", "default": True},
            },
            ["claim"],
        ),
        output_schema=_object_schema(
            {
                "asset_classes": {"type": "array", "items": {"type": "string"}},
                "source_ids": {"type": "array", "items": {"type": "string"}},
                "available_source_ids": {"type": "array", "items": {"type": "string"}},
                "series_mappings": {"type": "array", "items": {"type": "object"}},
                "source_descriptions": {"type": "array", "items": {"type": "object"}},
                "unmapped_asset_classes": {"type": "array", "items": {"type": "string"}},
            }
        ),
    )


def _load_source_documentation_tool() -> RegisteredTool:
    return RegisteredTool(
        name="load_source_documentation",
        description="Load local API playbooks and source documentation for selected data sources.",
        when_to_use=(
            "Use after map_asset_sources or select_sources, before retrieval, when the agent needs endpoint schemas, "
            "auth env vars, symbol naming rules, parameter names, response fields, or source-specific caveats."
        ),
        data_sources=["Local source_descriptions/*.md API playbooks"],
        requires_keys=[],
        limitations=[
            "Loads the repo-local documentation cache; it does not browse the internet or update docs automatically.",
            "External API docs can change, so adapters should still preserve provider errors in audit notes.",
        ],
        input_schema=_object_schema(
            {
                "source_ids": {"type": "array", "items": {"type": "string"}},
                "source_id": {"type": "string"},
                "claim": {
                    "type": "string",
                    "description": "Optional claim; if source_ids are omitted the tool selects likely sources first.",
                },
                "include_planned_sources": {"type": "boolean", "default": False},
            },
        ),
        output_schema=_object_schema(
            {
                "source_ids": {"type": "array", "items": {"type": "string"}},
                "details": {"type": "array", "items": {"type": "object"}},
                "missing_source_ids": {"type": "array", "items": {"type": "string"}},
            }
        ),
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
        description="Choose source adapters by combining claim intent with detected asset class.",
        when_to_use="Use after entity extraction and claim decomposition to decide whether the claim needs issuer fundamentals, equity/ETF/index prices, macro/rates/FX/commodity time series, fixed-income/credit data, or derivatives positioning.",
        data_sources=[],
        requires_keys=[],
        limitations=["Local route planner; the retrieval layer still determines which sources are actually available and entitled."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "official_only": {"type": "boolean", "default": True},
                "asset_classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional asset classes from extract_entities/map_asset_sources, e.g. single_name_equity, commodity, rates, fx.",
                },
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
                "entities": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional extracted entities containing asset_class; improves tool/source gating.",
                },
                "asset_classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional asset classes from entity extraction or map_asset_sources.",
                },
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
        limitations=[
            "Concept selection is keyword-based, not a full XBRL semantic planner.",
            "Do not use for merger, acquisition, takeover, stake, product-market, or management-quote claims.",
        ],
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


def _get_income_statement_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_income_statement",
        description="Retrieve structured income statement rows (revenue, gross profit, operating income, net income, EPS) for multiple periods.",
        when_to_use=(
            "Use when a claim asserts specific income-statement figures such as revenue, net income, gross profit, operating income, "
            "EPS, or margins for one or more fiscal periods. Prefer over get_sec_company_facts when you need a multi-period table "
            "rather than a concept-filtered snippet."
        ),
        data_sources=["SEC EDGAR XBRL company facts (primary)", "Financial Modeling Prep (fallback)"],
        requires_keys=["No key needed for SEC path; FMP_API_KEY optional for fallback"],
        limitations=[
            "XBRL figures are as-reported and may differ from adjusted/non-GAAP metrics.",
            "Very recent quarters may not yet be filed with SEC.",
        ],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string", "description": "Equity ticker symbol, e.g. AAPL."},
                "period": {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"},
                "limit": {"type": "integer", "default": 4, "description": "Number of periods to return (1–8)."},
            },
            ["ticker"],
        ),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _get_balance_sheet_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_balance_sheet",
        description="Retrieve structured balance sheet rows (assets, liabilities, equity, cash, debt) for multiple periods.",
        when_to_use=(
            "Use when a claim asserts balance-sheet figures: total assets, liabilities, stockholders' equity, cash position, "
            "long-term debt, current ratio, or working capital."
        ),
        data_sources=["SEC EDGAR XBRL company facts (primary)", "Financial Modeling Prep (fallback)"],
        requires_keys=["No key needed for SEC path; FMP_API_KEY optional"],
        limitations=[
            "Balance-sheet snapshots are point-in-time; ensure the period end matches the claim's reference date.",
        ],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "period": {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"},
                "limit": {"type": "integer", "default": 4},
            },
            ["ticker"],
        ),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _get_cash_flow_statement_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_cash_flow_statement",
        description="Retrieve structured cash flow statement rows (operating, investing, financing CF; capex; free cash flow).",
        when_to_use=(
            "Use when a claim asserts cash flow figures: operating cash flow, free cash flow, capex, "
            "or investing/financing activities for a specific period."
        ),
        data_sources=["SEC EDGAR XBRL company facts (primary)", "Financial Modeling Prep (fallback)"],
        requires_keys=["No key needed for SEC path; FMP_API_KEY optional"],
        limitations=[
            "Free cash flow is computed as operatingCF minus absolute capex; does not include working-capital adjustments.",
        ],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "period": {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"},
                "limit": {"type": "integer", "default": 4},
            },
            ["ticker"],
        ),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _get_earnings_history_tool() -> RegisteredTool:
    return RegisteredTool(
        name="get_earnings_history",
        description="Retrieve quarterly EPS history with beat/miss vs. analyst estimates.",
        when_to_use=(
            "Use when a claim asserts an EPS figure, an earnings beat or miss, 'kept beating quarter after quarter', "
            "or a pattern of earnings surprises. This tool returns actual vs. estimated EPS for recent quarters."
        ),
        data_sources=["SEC EDGAR XBRL company facts (EPS)", "Financial Modeling Prep earnings surprises (optional)"],
        requires_keys=["No key needed for SEC EPS history; FMP_API_KEY for beat/miss estimates"],
        limitations=[
            "Beat/miss data requires FMP_API_KEY; without it only reported EPS is returned.",
            "EPS figures are GAAP diluted unless otherwise noted.",
        ],
        input_schema=_object_schema(
            {
                "ticker": {"type": "string"},
                "limit": {"type": "integer", "default": 8, "description": "Number of quarters to return."},
            },
            ["ticker"],
        ),
        output_schema=_object_schema({"results": _search_result_array(), "notes": {"type": "array"}}),
    )


def _retrieve_evidence_tool() -> RegisteredTool:
    return RegisteredTool(
        name="retrieve_evidence",
        description="Retrieve and normalize evidence for a claim without final verification.",
        when_to_use=(
            "Use when the agent wants evidence objects first, then plans to call verification tools separately. "
            "Infer the claim's event/release/trading date from the surrounding context and pass it as as_of_date."
        ),
        data_sources=["Configured structured sources", "Optional Serper", "Optional Jina Reader"],
        requires_keys=["Optional provider keys depending on configured sources"],
        limitations=["Does not run LLM semantic verification by itself."],
        input_schema=_object_schema(
            {
                "claim": {"type": "string"},
                "ticker": {"type": "string"},
                "as_of_date": {"type": "string"},
                "max_sources": {"type": "integer", "default": 8},
                "selected_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Provider/source ids selected by select_sources. Empty array means do not retrieve.",
                },
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


def _audit_verification_chain_tool() -> RegisteredTool:
    return RegisteredTool(
        name="audit_verification_chain",
        description="Audit a completed report, evidence pack, audit trace, or agent trace for verification-chain quality and source/claim common sense.",
        when_to_use="Use after a credibility report or agent trace exists and the agent needs independent review of evidence, computation, tool use, constraints, reasoning, source relevance, no-evidence handling, or outcome handling.",
        data_sources=["Provided report payload", "Provided EvidencePack", "Provided AuditTrace", "Provided AgentTrace"],
        requires_keys=["Optional OPENAI_API_KEY or ANTHROPIC_API_KEY for narrow reasoning review"],
        limitations=[
            "Deterministic checks are strongest for evidence URLs, canonical fact ids, numeric derivations, and tool order.",
            "Common-sense checks are heuristic: they flag likely source/claim mismatches and no-displayable-source gaps for human review.",
            "Reasoning review is narrow and should not introduce new facts.",
            "Outcome references are optional and never override evidence-based verification.",
        ],
        input_schema=_object_schema(
            {
                "report_payload": {"type": "object"},
                "evidence_pack": {"type": "object"},
                "audit_trace": {"type": "object"},
                "agent_trace": {"type": "object"},
                "outcome_reference": {"type": "object"},
            }
        ),
        output_schema={"type": "object"},
    )


def _summarize_evidence_pack_tool() -> RegisteredTool:
    return RegisteredTool(
        name="summarize_evidence_pack",
        description="Summarize an evidence pack or report payload for team review.",
        when_to_use="Use when a human reviewer needs a compact explanation of entities checked, claim verdicts, evidence, confidence, and human-review reasons.",
        data_sources=["Provided report payload", "Provided EvidencePack"],
        requires_keys=[],
        limitations=["Summary is extractive and does not change verdicts."],
        input_schema=_object_schema(
            {
                "report_payload": {"type": "object"},
                "evidence_pack": {"type": "object"},
            }
        ),
        output_schema=_object_schema(
            {
                "summary": {"type": "string"},
                "entities": {"type": "array", "items": {"type": "object"}},
                "claims": {"type": "array", "items": {"type": "object"}},
                "human_review_count": {"type": "integer"},
            }
        ),
    )


def _summarize_audit_report_tool() -> RegisteredTool:
    return RegisteredTool(
        name="summarize_audit_report",
        description="Summarize audit findings by severity, category, and recommended next action.",
        when_to_use="Use after audit_verification_chain when a human needs a concise QA summary.",
        data_sources=["Provided AuditReport"],
        requires_keys=[],
        limitations=["Does not rerun audit checks; it only summarizes an existing report."],
        input_schema=_object_schema(
            {
                "audit_report": {"type": "object"},
            },
            ["audit_report"],
        ),
        output_schema=_object_schema(
            {
                "summary": {"type": "string"},
                "counts_by_severity": {"type": "object"},
                "counts_by_category": {"type": "object"},
                "top_findings": {"type": "array", "items": {"type": "object"}},
            }
        ),
    )


def _review_tool_surface_tool() -> RegisteredTool:
    return RegisteredTool(
        name="review_tool_surface",
        description="Review registered tool descriptions and profiles for ambiguity, overlap, missing parameter guidance, and excessive surface area.",
        when_to_use="Use before exposing tools to a model, after adding new tools, or when an agent appears to misuse tools.",
        data_sources=["Tool registry", "Tool profiles"],
        requires_keys=[],
        limitations=["Static review only; it does not execute tools or evaluate model behavior on examples."],
        input_schema=_object_schema(
            {
                "profile": {"type": "string", "description": "Optional tool profile name to review."},
            }
        ),
        output_schema=_object_schema(
            {
                "findings": {"type": "array", "items": {"type": "object"}},
                "tool_count": {"type": "integer"},
                "profile": {"type": "string"},
            }
        ),
    )


def _required_prior_state(name: str) -> str:
    if name == "preprocess_statement":
        return "Raw user-pasted statement, article, webpage text, transcript, or financial statement."
    if name == "map_asset_sources":
        return "A specific claim; extracted entities are useful but optional."
    if name == "load_source_documentation":
        return "Selected source ids from map_asset_sources/select_sources, or a claim so the tool can infer likely source ids."
    if name in {"get_income_statement", "get_balance_sheet", "get_cash_flow_statement", "get_earnings_history"}:
        return "A resolved ticker; optionally the period (annual/quarterly) and limit."
    if name in {"retrieve_evidence", "select_sources", "route_sources"}:
        return "A specific claim plus detected entities or asset_classes when available; for retrieval, a resolved ticker or explicit ticker hint and the inferred event/release/trading date when available."
    if name in {"get_canonical_facts", "verify_atomic_claim", "verify_numeric_claim", "verify_logic_claim", "verify_source_quality", "aggregate_credibility"}:
        return "Evidence or structured search results produced by retrieval/source tools."
    if name in {"build_audit_trace", "audit_verification_chain", "summarize_audit_report"}:
        return "A completed workflow, report payload, evidence pack, or trace object."
    if name in {"summarize_evidence_pack"}:
        return "A report payload or EvidencePack-like object."
    if name in {"review_tool_surface"}:
        return "No workflow state required; optionally pass a profile name."
    return "No prior tool state required unless the input schema includes optional evidence or search result fields."


def _do_not_use_when(name: str) -> str:
    if name == "preprocess_statement":
        return "the input is already a short, manually written atomic claim and no copied-page boilerplate is present."
    if name == "map_asset_sources":
        return "the claim is a simple US public-company reported metric already routed directly to SEC facts."
    if name == "load_source_documentation":
        return "the selected source documentation has already been loaded and still matches the source ids being used."
    if name == "build_evidence_pack":
        return "the agent needs fine-grained multi-step control or must inspect intermediate evidence before deciding."
    if name in {"get_income_statement", "get_balance_sheet", "get_cash_flow_statement", "get_earnings_history"}:
        return "the claim does not assert a specific financial statement figure, or the data for that period is already available from a prior retrieval."
    if name.startswith("get_"):
        return "the needed evidence is already available in prior tool output and still matches the claim/time window."
    if name.startswith("verify_"):
        return "retrieval has not produced evidence or canonical facts for the claim."
    if name == "aggregate_credibility":
        return "evidence has not been scored or the user needs claim-level reasons rather than a global score."
    if name.startswith("summarize_"):
        return "the underlying report or audit object has not been created."
    if name == "audit_verification_chain":
        return "there is no report, evidence pack, audit trace, or agent trace to review."
    return "the tool's required inputs are not known or a higher-level tool already provides the requested result."


def _output_means(name: str) -> str:
    if name == "preprocess_statement":
        return "a cleaned statement plus audit metadata about removed boilerplate; use cleaned_statement for all downstream tools."
    if name == "map_asset_sources":
        return "planning metadata that tells the agent which source/series/endpoint should be tried next."
    if name == "load_source_documentation":
        return "source-specific API playbooks with endpoint schemas, auth env vars, naming rules, response fields, and caveats."
    if name in {"get_income_statement", "get_balance_sheet", "get_cash_flow_statement", "get_earnings_history"}:
        return "structured financial statement rows with period-end dates and line-item values; pass results to get_canonical_facts or verify_numeric_claim."
    if name in {"retrieve_evidence", "get_sec_company_facts", "get_recent_filings", "get_company_fundamentals"}:
        return "candidate source records that still need canonicalization or verification before final claims."
    if name == "get_canonical_facts":
        return "normalized facts with provenance ids suitable for numeric and claim-level verification."
    if name.startswith("verify_") or name == "calibrate_uncertainty":
        return "claim-level or dimension-level verification results, not a standalone user-facing report."
    if name == "audit_verification_chain":
        return "audit findings and severity labels for workflow quality assurance."
    if name.startswith("summarize_"):
        return "human-readable review summary extracted from existing structured outputs."
    if name == "review_tool_surface":
        return "static findings about tool descriptions and profile design."
    return "structured JSON that should be fed into the next appropriate tool or final report step."


def _recommended_next_tools(name: str) -> str:
    mapping = {
        "preprocess_statement": "extract_entities and decompose_claims using cleaned_statement.",
        "extract_entities": "map_asset_sources, then decompose_claims and select_sources or retrieve_evidence for each verifiable claim.",
        "map_asset_sources": "load_source_documentation or select_sources, then retrieve_evidence or source-specific retrieval tools.",
        "load_source_documentation": "retrieve_evidence or source-specific retrieval tools using the documented endpoint/schema rules.",
        "decompose_claims": "classify_claim or select_sources for factual claims; skip opinion/forecast unless the user asks for reasoning review.",
        "select_sources": "retrieve_evidence or source-specific retrieval tools.",
        "route_sources": "source-specific retrieval tools or retrieve_evidence.",
        "get_income_statement": "get_canonical_facts using the results, then verify_numeric_claim or verify_atomic_claim.",
        "get_balance_sheet": "get_canonical_facts using the results, then verify_numeric_claim or verify_atomic_claim.",
        "get_cash_flow_statement": "get_canonical_facts using the results, then verify_numeric_claim or verify_atomic_claim.",
        "get_earnings_history": "verify_numeric_claim or verify_logic_claim using the EPS rows.",
        "get_sec_company_facts": "get_canonical_facts, then verify_atomic_claim.",
        "get_recent_filings": "retrieve_evidence or verify_source_quality if filing context is sufficient.",
        "retrieve_evidence": "get_canonical_facts, verify_numeric_claim, verify_logic_claim, verify_source_quality.",
        "get_canonical_facts": "verify_atomic_claim, then build_audit_trace.",
        "verify_atomic_claim": "calibrate_uncertainty or build_audit_trace.",
        "verify_numeric_claim": "verify_logic_claim and verify_source_quality, then aggregate_credibility.",
        "verify_logic_claim": "verify_source_quality, then aggregate_credibility.",
        "verify_source_quality": "aggregate_credibility or build_audit_trace.",
        "aggregate_credibility": "build_audit_trace or summarize_evidence_pack.",
        "build_audit_trace": "audit_verification_chain.",
        "build_evidence_pack": "audit_verification_chain or summarize_evidence_pack.",
        "audit_verification_chain": "summarize_audit_report.",
        "summarize_evidence_pack": "audit_verification_chain if QA is needed.",
        "summarize_audit_report": "human review or tool/prompt refinement.",
        "review_tool_surface": "edit tool descriptions or profile membership.",
    }
    return mapping.get(name, "Use the output in the next verifier, summary, or audit step that matches the user's goal.")
