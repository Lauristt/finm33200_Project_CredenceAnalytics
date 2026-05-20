# Financial Credibility Toolkit

Provider-neutral credibility tools for US equity financial claims. The project is
designed to be called by an LLM agent as a tool package, while keeping retrieval,
evidence construction, verification, and scoring inspectable for developers.

The default mode is useful-first rather than strictly reproducible:

- Retrieve structured financial evidence from free/free-tier data sources.
- Extract evidence objects with source authority, recency, relevance, and numeric
  consistency scores.
- Use local fuzzy numeric matching before any LLM call.
- Use OpenAI or Anthropic for narrow semantic checks when configured.
- Return numeric confidence, logic confidence, source confidence, and an English
  overall label.

## Repository Layout

```text
agent_build/
  pyproject.toml
  README.md
  TOOLS.md
  .env.example
  examples/
  src/financial_credibility/
    adapters.py          # OpenAI/Anthropic tool schema adapters.
    aggregation.py       # Deterministic weighted credibility score.
    argument.py          # Claim type classifier.
    cli.py               # CLI entry point.
    config.py            # Env/config loading.
    data_sources.py      # SEC, Alpha Vantage, Finnhub, FMP, FRED, etc.
    extraction.py        # SearchResult -> Evidence conversion.
    judges.py            # Heuristic/OpenAI/Anthropic semantic judges.
    models.py            # Dataclasses and enums shared across the package.
    modes/
      agentic.py         # Default exploratory wrapper.
      strict.py          # Thin strict-mode wrapper.
    net.py               # urllib helper with cert handling.
    price_history.py     # Historical price extraction and oscillation features.
    rubrics.py           # Argument-type scoring weights.
    search.py            # Structured retrieval plus optional Serper.
    sources.py           # Source authority, recency, numeric scoring.
    text.py              # Token overlap utilities.
    tool_registry.py     # Agent-facing tool metadata and JSON schemas.
    tool_runtime.py      # Execute registered tools by name.
    toolkit.py           # Main orchestration API.
    verification.py      # Numeric, logic, source, and overall checks.
  tests/
```

## Installation And Build

The package currently has no required third-party Python dependencies.

Editable install for local development:

```bash
cd /Users/laurisli/Desktop/FINM33200/final_project/agent_build
python3 -m pip install -e .
```

Run from source without installing:

```bash
PYTHONPATH=src python3 -m financial_credibility \
  "Apple revenue grew 6% year over year in the latest quarter." \
  --ticker AAPL \
  --pretty
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Compile check:

```bash
PYTHONPATH=src python3 -m compileall src tests
```

Build a wheel/sdist if the `build` package is installed:

```bash
python3 -m build
```

## Configuration

Copy `.env.example` to `.env`. `.env` is intentionally ignored by git.

```text
OPENAI_API_KEY=
OPENAI_MODEL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
CREDIBILITY_LLM_PROVIDER=auto

SERPER_API_KEY=
JINA_API_KEY=
FINNHUB_API_KEY=
ALPHA_VANTAGE_API_KEY=
FMP_API_KEY=
FRED_API_KEY=
MARKETSTACK_API_KEY=
TIINGO_API_KEY=
SEC_USER_AGENT=
```

Important flags:

- `CREDIBILITY_LLM_PROVIDER=auto|openai|anthropic`: choose semantic judge.
- `CREDIBILITY_STRUCTURED_SOURCES=true|false`: enable free structured sources.
- `CREDIBILITY_LIVE_EXTRACTION=true|false`: fetch article/page text through Jina
  Reader instead of using snippets only.
- `CREDIBILITY_YAHOO_FALLBACK=true|false`: enable unofficial Yahoo chart fallback.
- `CREDIBILITY_REQUEST_TIMEOUT=25`: network timeout in seconds.

If no LLM key/model is configured, the package falls back to `HeuristicJudge`.

## Main Developer API

### `FinancialCredibilityToolkit`

Located in `src/financial_credibility/toolkit.py`.

```python
from financial_credibility import FinancialCredibilityToolkit

toolkit = FinancialCredibilityToolkit.from_env()
pack = toolkit.build_evidence_pack(
    claim="Apple reported revenue of 416161000000 in fiscal 2025.",
    ticker="AAPL",
    as_of_date="2026-05-19",
    max_sources=10,
)
print(pack.to_dict())
```

`build_evidence_pack(...)` is the main orchestration function. It performs:

1. Argument classification with `classify_argument_type`.
2. Retrieval with `SearchClient.search_financial_sources`.
3. Evidence extraction with `EvidenceExtractor.extract`.
4. Per-source semantic judging with `SemanticJudge`.
5. Source independence scoring.
6. Weighted scoring with `aggregate_scores`.
7. Explicit numeric, logic, source, and overall verification.
8. Returns an `EvidencePack`.

Use `prefetched_results` for deterministic tests or demos without network calls:

```python
pack = toolkit.build_evidence_pack(
    claim="Apple revenue grew 6% year over year.",
    ticker="AAPL",
    prefetched_results=[
        {
            "title": "Apple reports fourth quarter results",
            "url": "https://www.apple.com/newsroom/example",
            "snippet": "Apple reported quarterly revenue up 6 percent year over year.",
            "published_at": "2025-10-30",
        }
    ],
)
```

### Agentic Mode

`modes/agentic.py` contains `AgenticCredibilityRunner`. It does not create
autonomous sub-agents. It adds extra search-plan queries, including contradiction
and official-source queries, then calls the same underlying toolkit pipeline.

CLI default:

```bash
PYTHONPATH=src python3 -m financial_credibility \
  "Apple reported revenue of 416161000000 in fiscal 2025." \
  --ticker AAPL \
  --mode agentic
```

Strict mode:

```bash
PYTHONPATH=src python3 -m financial_credibility \
  "Apple reported revenue of 416161000000 in fiscal 2025." \
  --ticker AAPL \
  --mode strict
```

## Core Data Model

All shared types are in `models.py`.

- `SearchResult`: raw retrieval item from an API, search engine, or prefetched
  JSON.
- `Evidence`: normalized source-level evidence with scores and notes.
- `ScoreBreakdown`: deterministic weighted scoring dimensions.
- `VerificationCheck`: explicit check result for numeric, logic, or source
  confidence.
- `OverallConclusion`: user-facing label and confidence summary.
- `EvidencePack`: final output object returned by the toolkit.
- `ToolSpec`: provider-agnostic tool definition that can be exported to OpenAI
  or Anthropic schemas.

Typical output shape:

```json
{
  "claim": "...",
  "ticker": "AAPL",
  "argument_type": "metric_fact",
  "credibility_score": 0.778,
  "numeric_check": {"verdict": "verified", "method": "fuzzy_local"},
  "logic_check": {"verdict": "partially_verified", "method": "anthropic"},
  "source_check": {"verdict": "partially_verified", "method": "scoring"},
  "overall_conclusion": {"overall_label": "High"}
}
```

## Pipeline Details

### 1. Argument Classification

`argument.py`

- `classify_argument_type(claim)`: rule-based classifier for:
  - `metric_fact`
  - `event_fact`
  - `attribution_fact`
  - `opinion_analysis`
  - `forecast`
- `_needs_decomposition(claim)`: marks long or multi-part claims.

The argument type selects rubric weights. For example, metric facts emphasize
numeric consistency; forecasts emphasize reasoning quality and independence.

### 2. Retrieval

`search.py`

- `SearchClient.search_financial_sources(...)`: top-level retrieval method.
- `build_queries(...)`: creates argument-type-specific web-search queries.
- `_normalize_result(...)`: converts dicts and existing `SearchResult` objects
  into the same internal shape.

Retrieval order:

1. Use `prefetched_results` when provided.
2. Query structured free/free-tier sources via `FreeDataSourceClient`.
3. If configured, query Serper web search.

### 3. Structured Data Sources

`data_sources.py`

`FreeDataSourceClient.query(...)` calls providers in order until `max_results` is
reached. Provider methods return `SearchResult` objects, not final evidence.

Implemented providers:

- `historical_prices(ticker, claim, as_of_date)`: daily historical prices from
  Alpha Vantage, FMP, Finnhub, or Stooq fallback for price-pattern claims such
  as oscillating, volatile, range-bound, or trending over a lookback window.
- `sec_company_facts(claim, ticker)`: SEC XBRL company facts.
- `sec_recent_filings(ticker)`: recent SEC 10-K, 10-Q, and 8-K filings.
- `alpha_vantage(ticker)`: company overview and earnings.
- `finnhub(ticker)`: profile and basic financial metrics.
- `fmp(ticker)`: profile and income statement.
- `fred(claim)`: macro series selected from claim keywords.
- `marketstack(ticker)`: latest EOD quote.
- `tiingo(ticker)`: recent EOD price.
- `stooq(ticker)`: latest free quote, no key needed.
- `yahoo_chart(ticker)`: unofficial chart fallback, disabled by default.

To add a new provider:

1. Add a method returning `list[SearchResult]`.
2. Add it to the `providers` list in `FreeDataSourceClient.query`.
3. Add a source authority mapping in `sources.DOMAIN_AUTHORITY`.
4. Add a focused unit test using mocked or prefetched data.

### 4. Evidence Extraction

`extraction.py`

- `EvidenceExtractor.extract(...)`: converts `SearchResult` into scored
  `Evidence`.
- `score_relevance(...)`: lexical overlap plus entity/ticker bonus.
- `score_entity_match(...)`: detects ticker or known company aliases.

Extraction assigns:

- source type and authority from `assess_source`
- recency from `score_recency`
- numeric consistency from `score_numeric_consistency`
- relevance and entity match scores

If `CREDIBILITY_LIVE_EXTRACTION=true`, extractor uses Jina Reader to fetch page
text; otherwise it uses snippets from retrieval providers.

### Historical Price Extractor

`price_history.py`

Price-pattern claims need time-series evidence rather than only fundamentals.
For claims such as "NVDA's stock price seems to be oscillating over 10 months",
the retrieval layer calls `historical_prices(...)`, which uses configured daily
price providers and formats a compact evidence snippet with:

- start/end close
- min/max close
- total return
- price range percentage
- annualized volatility
- daily and monthly direction changes
- `oscillation_signal` as `weak`, `moderate`, or `strong`

Main helper functions:

- `needs_historical_price_data(claim)`: detects price-pattern claims.
- `parse_lookback_months(claim)`: converts "10 months", "40 weeks", or "1 year"
  into an approximate month window.
- `parse_stooq_price_csv(text)`: parses Stooq CSV into daily `PricePoint` rows.
- `summarize_price_history(points)`: computes volatility/range/direction-change
  features.
- `format_price_history_summary(ticker, lookback_months, summary)`: creates the
  dense snippet passed downstream to the judge.

### 5. Semantic Judges

`judges.py`

- `SemanticJudge`: abstract interface.
- `HeuristicJudge`: local no-key fallback.
- `OpenAIJudge`: narrow JSON judge through OpenAI chat completions.
- `AnthropicJudge`: narrow JSON judge through Anthropic messages.
- `create_judge(config)`: chooses a judge from env/config.

Judge methods:

- `judge_evidence_support(claim, evidence)`: supports/contradicts/not enough info.
- `judge_independence(first, second)`: source independence score.
- `judge_reasoning_quality(claim, evidence, argument_type)`: quality of reasoning.
- `judge_numeric_claim(claim, evidence)`: LLM fallback for numeric verification.
- `judge_logic_claim(claim, evidence, argument_type)`: semantic logic check.

The LLM judge is deliberately narrow: each call asks for one small JSON judgment
instead of a global credibility score.

### 6. Aggregation

`aggregation.py`

- `aggregate_scores(argument_type, evidence, risk_flags)`: computes the legacy
  deterministic credibility score and label.

Score dimensions:

- source authority
- recency
- evidence support
- numeric consistency
- independence
- reasoning quality
- penalties

Weights live in `rubrics.py` and differ by argument type.

### 7. Explicit Verification

`verification.py`

- `verify_numeric_claim(claim, evidence, judge)`: fuzzy local numeric matching
  first; LLM fallback only when no local match is found. Temporal lookback
  durations such as "10 months" are ignored so they do not falsely verify a
  price-pattern claim.
- `verify_logic_claim(claim, evidence, argument_type, judge)`: asks the configured
  semantic judge whether the inference or reasoning is supported.
- `verify_sources(evidence, breakdown)`: source-quality confidence from authority,
  independence, and recency.
- `build_overall_conclusion(...)`: combines numeric, logic, and source confidence
  into `Very High`, `High`, `Medium`, `Low`, or `Contradicted`.

`_rank_evidence_for_verification(...)` prioritizes evidence with numeric matches
and strong support before sending snippets to the LLM, so the judge sees the most
relevant sources within the token budget.

## Agent Tool Layer

The package exposes both one-shot orchestration and atomic tools. The human and
agent-facing manual is [TOOLS.md](TOOLS.md).

Core files:

- `tool_registry.py`: declarative metadata for every tool, including schema,
  when-to-use guidance, data sources, required keys, and limitations.
- `tool_runtime.py`: executes a registered tool by name with JSON arguments.
- `adapters.py`: exports the registered tools to OpenAI or Anthropic schemas.

Registered tools:

- `classify_claim`
- `get_sec_company_facts`
- `get_recent_filings`
- `get_company_fundamentals`
- `get_historical_prices`
- `compare_stock_performance`
- `retrieve_evidence`
- `verify_numeric_claim`
- `verify_logic_claim`
- `verify_source_quality`
- `aggregate_credibility`
- `build_evidence_pack`

Example:

```python
from financial_credibility import ToolkitConfig, execute_tool

config = ToolkitConfig.from_env()
result = execute_tool(
    "get_historical_prices",
    {
        "ticker": "MSFT",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
    },
    config,
)
```

The high-level tool remains available:

```python
pack = execute_tool(
    "build_evidence_pack",
    {
        "claim": "Microsoft performed poorly last year.",
        "ticker": "MSFT",
        "as_of_date": "2026-05-20",
    },
    config,
)
```

## Tool Schema Adapters

`adapters.py`

```python
from financial_credibility.adapters import export_anthropic_tools, export_openai_tools

openai_tools = export_openai_tools()
anthropic_tools = export_anthropic_tools()
```

Use these schemas in an OpenAI tool/function registration flow or an Anthropic
tool-use flow. The actual execution endpoint should call:

```python
from financial_credibility import execute_tool

result = execute_tool(tool_name, tool_args)
```

## CLI

The CLI is defined in `cli.py`.

```bash
financial-credibility "Claim text" --ticker AAPL --pretty
```

Useful flags:

- `--ticker AAPL`
- `--as-of-date 2026-05-19`
- `--max-sources 10`
- `--mode strict|agentic`
- `--env-file path/to/.env`
- `--prefetched-json examples/prefetched_aapl.json`
- `--pretty`

## Development Notes

- Keep `.env` out of git; put only placeholders in `.env.example`.
- Prefer adding providers as `SearchResult` producers, not direct `Evidence`
  producers. This keeps extraction and scoring centralized.
- Keep LLM tasks narrow and JSON-shaped. The aggregator should not rely on a
  free-form global LLM credibility score.
- Use `prefetched_results` in tests when possible to avoid flaky network calls.
- When adding a new score field, update `models.ScoreBreakdown`, `rubrics.py`,
  `aggregation.py`, and tests together.

## Current Limitations

- Source extraction is snippet-first unless Jina Reader is enabled.
- Yahoo Finance support is unofficial and disabled by default.
- SEC company facts are concept-mapped by simple keywords, not a full XBRL query
  planner.
- The system focuses on US equities; macro support exists only through limited
  FRED keyword matching.
