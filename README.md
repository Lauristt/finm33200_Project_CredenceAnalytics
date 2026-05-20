# Financial Credibility Toolkit

Provider-neutral credibility tools for US equity financial claims.

The package exposes a shared retrieval/evidence/scoring system with two modes:

- `agentic` default: exploratory wrapper that expands search strategy, but still uses the same verifier.
- `strict`: fixed pipeline for controlled experiments.

The main entry point is `build_evidence_pack(claim, ticker, ...)`. The output includes:

- `numeric_check`: whether numbers/periods/units are verified.
- `logic_check`: whether the reasoning or inference is supported.
- `source_check`: whether evidence quality is strong enough.
- `overall_conclusion`: English overall label and confidence.

## Quick Start

```bash
cd agent_build
PYTHONPATH=src python -m financial_credibility "Apple revenue grew 6% year over year in the latest quarter." --ticker AAPL
```

Without API keys, pass pre-fetched search results:

```bash
PYTHONPATH=src python -m financial_credibility \
  "Apple revenue grew 6% year over year in the latest quarter." \
  --ticker AAPL \
  --prefetched-json examples/prefetched_aapl.json
```

Or install locally:

```bash
python -m pip install -e .
financial-credibility "Apple revenue grew 6% year over year in the latest quarter." --ticker AAPL
```

## Configuration

Copy `.env.example` to `.env` and fill only the keys you need.

```text
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
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

The default judge mode is `auto`: it uses OpenAI or Anthropic when both the API key
and model name are configured, otherwise it falls back to the local heuristic judge.

```text
CREDIBILITY_LLM_PROVIDER=auto
OPENAI_API_KEY=
OPENAI_MODEL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
```

Numeric verification first uses local fuzzy matching. If a number is matched directly,
the numeric check passes without an LLM call. If no number matches, the toolkit asks
the configured LLM judge to verify the numeric claim.

## Free Data Sources

The retrieval layer can query multiple free or free-tier sources:

- SEC EDGAR company facts and recent filings: no key; set `SEC_USER_AGENT`.
- Stooq latest quote: no key.
- Alpha Vantage: `ALPHA_VANTAGE_API_KEY`.
- Finnhub: `FINNHUB_API_KEY`.
- Financial Modeling Prep: `FMP_API_KEY`.
- FRED macro data: `FRED_API_KEY`.
- Marketstack: `MARKETSTACK_API_KEY`.
- Tiingo: `TIINGO_API_KEY`.
- Yahoo chart fallback: no key, unofficial, disabled unless `CREDIBILITY_YAHOO_FALLBACK=true`.

Set `CREDIBILITY_STRUCTURED_SOURCES=false` to disable structured source queries.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Python API

```python
from financial_credibility import FinancialCredibilityToolkit

toolkit = FinancialCredibilityToolkit.from_env()
pack = toolkit.build_evidence_pack(
    claim="Apple revenue grew 6% year over year in the latest quarter.",
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

print(pack.to_dict())
```

## Tool Schema Adapters

```python
from financial_credibility.adapters import build_evidence_pack_tool

spec = build_evidence_pack_tool()
openai_tool = spec.to_openai_tool_schema()
anthropic_tool = spec.to_anthropic_tool_schema()
```

## Design

The final score is deterministic:

```text
final_score =
  weight(source_authority) * source_authority
+ weight(recency) * recency
+ weight(evidence_support) * evidence_support
+ weight(numeric_consistency) * numeric_consistency
+ weight(independence) * independence
+ weight(reasoning_quality) * reasoning_quality
- penalties
```

Weights vary by argument type: `metric_fact`, `event_fact`,
`attribution_fact`, `opinion_analysis`, and `forecast`.

The more useful course-demo output is `overall_conclusion`, which combines numeric,
logic, and source confidence into an English label such as `High` or `Medium`.
