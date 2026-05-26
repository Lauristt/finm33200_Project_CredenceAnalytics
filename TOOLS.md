# Financial Credibility Tool Suite

This file is an agent-facing manual for the tools exposed by
`financial_credibility.tool_registry`. The tools are split into two levels:

- High-level orchestrator: `build_evidence_pack`
- Atomic tools: retrieval, price analysis, verification, and aggregation tools

Agents should use the high-level tool for simple one-shot checks and atomic
tools when the claim is vague, multi-part, or requires targeted evidence.

## Recommended Agent Pattern

For simple factual claims:

```text
build_evidence_pack(claim, ticker)
```

For multi-claim official verification:

```text
extract_entities(memo)
decompose_claims(claim)
resolve_entity(ticker, search_results/evidence)
select_sources(atomic_claim)
get_canonical_facts(ticker, search_results/evidence)
verify_atomic_claim(claim, ticker, evidence, canonical_facts)
build_audit_trace(claim, ticker, search_results, evidence, canonical_facts)
```

For vague performance or price-action claims:

```text
classify_claim(claim)
get_historical_prices(ticker, start_date, end_date)
get_company_fundamentals(ticker)
verify_logic_claim(claim, evidence)
verify_source_quality(evidence)
```

For relative performance claims:

```text
compare_stock_performance(ticker, benchmark_ticker, start_date, end_date)
verify_logic_claim(claim, evidence)
```

## Tool Reference

### classify_claim

Purpose:
Classify a claim into a rubric argument type.

Use When:
Use first when the agent needs to decide whether the claim is a metric fact,
event fact, attribution fact, opinion/analysis, or forecast.

Inputs:

- `claim`: financial claim text.

Outputs:

- `argument_type`
- `confidence`
- `signals`
- `needs_decomposition`

Data Sources:
None.

Limitations:
Rule-based routing. It is not a truth assessment.

### decompose_claims

Purpose:
Split a memo, paragraph, or compound sentence into atomic verifiable claims.

Outputs:

- `claims`: claim id, text, argument type, classification confidence, signals.

### extract_entities

Purpose:
Extract public companies, issuers, securities, and ticker hints from an
investment memo. Uses an optional OpenAI/Anthropic extractor plus deterministic
fallbacks. The high-level report UI calls this automatically when the entity
field is blank.

Outputs:

- `entities`
- `tickers`
- `unresolved_entities`
- `method`
- `notes`

### resolve_entity

Purpose:
Resolve ticker, CIK, LEI, FIGI, and evidence metadata into one entity mapping.

Outputs:

- `entity_id`
- `cik`
- `lei`
- `confidence`
- `issues`

### route_sources

Purpose:
Choose official source adapters for an atomic claim.

Outputs:

- `routes`
- `reasons`

### select_sources

Purpose:
Choose source ids from the governed source catalog with progressive disclosure.
The first pass shows only compact source cards. For the selected sources only,
the runtime loads local `source_descriptions/*.md` detail files and optionally
asks the configured OpenAI or Anthropic selector to refine the choice. The policy
validator then filters unknown ids and adds official primary sources when needed.

Outputs:

- `selections`
- `candidate_sources`
- `disclosure_stages`
- `selected_sources`
- `selected_source_details`
- `selected_provider_names`
- `rationale`
- `policy_notes`

### get_canonical_facts

Purpose:
Normalize SEC/FRED-style structured results or official evidence into canonical
facts with provenance and license metadata.

Outputs:

- `entity_resolution`
- `canonical_facts`

### verify_atomic_claim

Purpose:
Return claim-level verdicts with evidence keys, canonical fact ids, numeric
derivations, confidence components, and human-review flags.

### calibrate_uncertainty

Purpose:
Expose the same claim-level confidence decomposition and human-review triggers
used by `verify_atomic_claim`.

### build_audit_trace

Purpose:
Build a replayable audit trace for manual atomic workflows. The high-level
`build_evidence_pack` output already includes `audit_trace`.

### get_sec_company_facts

Purpose:
Retrieve SEC XBRL company facts relevant to a claim.

Use When:
Use for official numeric fundamentals: revenue, net income, EPS, margins, cash
flow, assets, liabilities, or debt.

Inputs:

- `ticker`
- `claim`

Outputs:

- `results`: compact `SearchResult` records
- `notes`

Data Sources:

- SEC EDGAR company facts

Requires Keys:
None. Set `SEC_USER_AGENT` for polite SEC access.

Limitations:
SEC concept selection is keyword-based.

### get_recent_filings

Purpose:
Retrieve recent 10-K, 10-Q, and 8-K filing links.

Use When:
Use when the agent needs official recent filing context.

Inputs:

- `ticker`

Outputs:

- `results`
- `notes`

Data Sources:

- SEC EDGAR submissions

Requires Keys:
None.

Limitations:
Returns filing metadata/snippets, not full parsed filings.

### get_company_fundamentals

Purpose:
Retrieve profile, earnings, income statement, and basic metrics snippets.

Use When:
Use for broad operating performance claims such as "performed poorly",
"earnings remain strong", "margins are healthy", or "growth is weak".

Inputs:

- `ticker`

Outputs:

- `results`
- `notes`

Data Sources:

- Alpha Vantage
- Finnhub
- Financial Modeling Prep

Requires Keys:

- `ALPHA_VANTAGE_API_KEY`
- `FINNHUB_API_KEY`
- `FMP_API_KEY`

The tool gracefully returns fewer results when some keys are missing.

Limitations:
Compact provider snippets only; not a full financial model.

### get_historical_prices

Purpose:
Retrieve daily historical prices and summarize price behavior.

Use When:
Use for claims about stock price performance, volatility, oscillation, trend,
drawdown, range-bound behavior, or a date-window return.

Inputs:

- `ticker`
- `start_date`: `YYYY-MM-DD`
- `end_date`: `YYYY-MM-DD`

Outputs:

- `provider`
- `summary.observations`
- `summary.start_close`
- `summary.end_close`
- `summary.total_return_pct`
- `summary.range_pct`
- `summary.annualized_volatility_pct`
- `summary.daily_direction_change_ratio`
- `summary.monthly_direction_change_ratio`
- `summary.oscillation_signal`
- `evidence_text`
- `evidence_url`

Data Sources:

- Alpha Vantage
- Financial Modeling Prep
- Finnhub
- Stooq fallback

Requires Keys:
At least one historical price provider key is recommended:

- `ALPHA_VANTAGE_API_KEY`
- `FMP_API_KEY`
- `FINNHUB_API_KEY`

Limitations:
Price-return based. Dividends and total return may not be included depending on
provider series.

### compare_stock_performance

Purpose:
Compare a stock's price return with a benchmark over the same window.

Use When:
Use for claims such as "underperformed the market", "beat the Nasdaq", or
"lagged peers".

Inputs:

- `ticker`
- `benchmark_ticker`
- `start_date`
- `end_date`

Outputs:

- `ticker_return_pct`
- `benchmark_return_pct`
- `relative_return_pct`
- `summary`
- nested historical price results for both series

Data Sources:
Same as `get_historical_prices`.

Limitations:
Uses price returns, not guaranteed total returns.

### retrieve_evidence

Purpose:
Retrieve and normalize evidence without final verification.

Use When:
Use when the agent wants to inspect evidence first, then call numeric/logic/source
verification separately.

Inputs:

- `claim`
- `ticker`
- `as_of_date` optional
- `max_sources` optional
- `prefetched_results` optional

Outputs:

- `argument_type`
- `classification`
- `evidence`
- `search_notes`
- `extraction_notes`

Data Sources:
Configured structured sources, optional Serper, optional Jina Reader.

Limitations:
Does not run LLM semantic verification by itself.

### verify_numeric_claim

Purpose:
Verify numeric values, periods, and units in a claim against evidence.

Use When:
Use after evidence retrieval for claims with explicit values such as revenue,
EPS, margins, market cap, or returns.

Inputs:

- `claim`
- `evidence`

Outputs:

- `verdict`
- `confidence`
- `summary`
- `evidence_urls`
- `issues`
- `method`

Data Sources:
Provided evidence.

Limitations:
Temporal lookback durations such as "10 months" are ignored as non-substantive
numeric facts, so price-pattern claims should be verified by logic/time-series
tools.

### verify_logic_claim

Purpose:
Verify whether a claim's reasoning or inference is supported by evidence.

Use When:
Use for semantic judgments: "performed poorly", "stock seems oscillating",
"earnings are strong", "valuation is expensive", "underperformed", or other
interpretive claims.

Inputs:

- `claim`
- `evidence`
- `argument_type` optional

Outputs:

- `verdict`
- `confidence`
- `summary`
- `evidence_urls`
- `issues`
- `method`

Data Sources:
Provided evidence plus OpenAI/Anthropic judge if configured.

Requires Keys:
Optional:

- `OPENAI_API_KEY` and `OPENAI_MODEL`
- `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`

Limitations:
Depends on evidence quality and the configured narrow LLM judge. Falls back to
heuristics when no LLM is configured or when the API call fails.

### verify_source_quality

Purpose:
Assess whether sources are authoritative, recent, and independent enough.

Use When:
Use after evidence retrieval to create the source-confidence dimension.

Inputs:

- `evidence`
- `argument_type` optional

Outputs:

- `verdict`
- `confidence`
- `summary`
- `evidence_urls`
- `issues`
- `method`

Data Sources:
Provided evidence.

Limitations:
Source independence is heuristic unless a semantic judge has already added
richer independence scores.

### aggregate_credibility

Purpose:
Aggregate evidence-level scores into a deterministic rubric score.

Use When:
Use when a glass-box score, verdict, and label are needed after evidence has
been gathered and judged.

Inputs:

- `evidence`
- `argument_type` optional
- `risk_flags` optional

Outputs:

- `score_breakdown`
- `verdict`
- `credibility_label`
- `risk_flags`

Data Sources:
Provided evidence.

Limitations:
This is a deterministic score. For user-facing conclusions, prefer combining
`verify_numeric_claim`, `verify_logic_claim`, and `verify_source_quality`.

### build_evidence_pack

Purpose:
Run the full end-to-end credibility pipeline.

Use When:
Use for simple one-shot credibility checks where the agent does not need to
manually plan retrieval and verification.

Inputs:

- `claim`
- `ticker`
- `as_of_date` optional
- `max_sources` optional
- `mode`: `agentic` or `strict`
- `prefetched_results` optional

Outputs:

- `verdict`
- `credibility_label`
- `credibility_score`
- `score_breakdown`
- `numeric_check`
- `logic_check`
- `source_check`
- `overall_conclusion`
- `evidence`
- `risk_flags`
- `metadata`

Data Sources:
All configured retrieval sources and optional LLM judge.

Limitations:
Less flexible than atomic tools for vague multi-part claims. Use atomic tools
when the agent needs to explicitly compare benchmarks, gather historical prices,
or separate stock-price and fundamental performance.
