# Financial Credibility Toolkit Report

Date: 2026-05-19

## 1. Project Positioning

The best scope for this project is not another full financial agent. It should be a provider-neutral, LLM-callable credibility tool package that any financial agent can call before trusting or citing search results.

Recommended project claim:

> A glass-box financial credibility toolkit for US equities that converts noisy web/search results into source-aware, evidence-backed, reproducible credibility scores.

This keeps the LLM provider flexible: OpenAI, Anthropic, or another model can be the agent brain. The contribution is the tool layer: retrieval, source typing, evidence extraction, semantic verification, and deterministic aggregation.

The existing Clarity project is useful as inspiration, but the new implementation should live independently in `agent_build`. Reusing the old agent architecture would make the final project harder to explain and harder to evaluate.

## 2. Recent Advances That Matter

### 2.1 Atomic Claims and Evidence-Level Verification

Recent factuality and RAG work increasingly avoids judging a whole answer in one step. Instead, it decomposes output into smaller claims or facts, retrieves evidence, and scores support at the evidence level.

Relevant work:

- [FActScore](https://arxiv.org/abs/2305.14251) evaluates long-form generation by breaking text into atomic facts and checking whether each fact is supported by retrieved knowledge.
- [SAFE](https://arxiv.org/abs/2403.18802) uses search-augmented checking for long-form factuality and shows that decomposed verification can scale better than manual review.
- [RAGChecker](https://arxiv.org/abs/2408.08067) proposes fine-grained diagnostics for retrieval-augmented generation, separating retrieval quality from generation faithfulness.

Design implication: credibility should be computed over evidence units and subclaims, not over an entire article or answer.

### 2.2 Retrieval Quality Is Multi-Dimensional

RAG evaluation has moved beyond "did the model answer correctly?" toward separate measurements for retrieval relevance, evidence coverage, citation quality, and faithfulness.

Relevant work:

- [RAGAS](https://arxiv.org/abs/2309.15217) frames RAG evaluation around answer faithfulness, context relevance, and answer relevance.
- [ARES](https://arxiv.org/abs/2311.09476) focuses on automated RAG evaluation across context relevance, answer faithfulness, and answer relevance.
- [TREC RAG Track](https://trec-rag.github.io/) treats RAG as a retrieval-plus-generation problem and emphasizes explicit evidence/nugget evaluation.

Design implication: the toolkit should expose separate scores for source authority, recency, relevance, support, independence, and numeric/date consistency. A single opaque credibility score is not enough.

### 2.3 LLM Judges Are Useful but Must Be Narrow

LLM-as-judge approaches are now common, but they are most defensible when the model is asked constrained, auditable questions. For this project, the LLM should not produce the final credibility score. It should answer narrow semantic questions such as:

- Does this evidence support, contradict, or fail to address the claim?
- Are these two sources independent, or is one merely repeating the other?
- Is this paragraph a factual report, opinion, forecast, or analysis?
- Is the article discussing the same company/entity and time period as the claim?

Design implication: the colleague's Layer 2 proposal is right. Use LLM calls only where deterministic rules are weak: semantic entailment, independence, argument type, and context matching.

### 2.4 Structured Tool Schemas Are Now a Stable Interface Pattern

Modern LLM providers support typed tool schemas. This matters because the toolkit can expose one internal JSON schema and then adapt it to OpenAI and Anthropic.

Relevant official docs:

- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) supports schema-constrained outputs and function/tool calling patterns.
- [Anthropic Tool Use](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use) defines tools with names, descriptions, and JSON input schemas.
- [Model Context Protocol](https://modelcontextprotocol.io/docs/concepts/tools) also represents tools through structured schemas, making future MCP support realistic.

Design implication: define provider-agnostic tool specifications first, then implement adapters:

- `to_openai_tool_schema()`
- `to_anthropic_tool_schema()`
- later: `to_mcp_tool_schema()`

### 2.5 Finance Needs Claim-Type-Specific Rubrics

Financial credibility is not one thing. A source can be highly credible for one claim type and weak for another.

Example:

- SEC 10-K revenue number: SEC filing is very authoritative.
- "NVDA is undervalued": no source can make this simply "true"; this is analysis/opinion.
- "A company will beat earnings next quarter": this is a forecast, so historical source authority is not enough.
- "Goldman Sachs says X": source authority establishes attribution, not truth.

Design implication: add an argument type classifier before scoring. The classifier should route each claim to a rubric.

## 3. Assessment of the Proposed Three-Layer Design

The proposed design is strong:

1. Deterministic base score
2. Narrow LLM/agent calls only for semantic judgments
3. Transparent weighted aggregation

I would make one modification: put argument type classification before Layer 1. So the architecture becomes:

```text
Layer 0: Argument type classifier
Layer 1: Deterministic checks
Layer 2: Narrow semantic LLM judges
Layer 3: Transparent aggregation
Layer 4: Tool/adapters exposed to financial agents
```

The reason is simple: the same evidence should be scored differently depending on the claim type. A recent opinion article and a recent SEC filing should not be treated as comparable evidence.

## 4. Proposed Architecture

### Layer 0: Argument Type Classifier

Input:

```json
{
  "claim": "Apple revenue grew 6% year over year in the latest quarter.",
  "ticker": "AAPL",
  "as_of_date": "2026-05-19"
}
```

Output:

```json
{
  "argument_type": "metric_fact",
  "confidence": 0.91,
  "reason": "The claim states a numeric historical company metric."
}
```

Initial types:

| Type | Meaning | Example |
|---|---|---|
| `metric_fact` | Historical numeric company/market metric | "Revenue was $X." |
| `event_fact` | Historical event or filing/news fact | "Company announced a buyback." |
| `attribution_fact` | A source/person said something | "Goldman downgraded X." |
| `opinion_analysis` | Interpretive claim | "The stock is overvalued." |
| `forecast` | Forward-looking claim | "Margins will expand next year." |
| `rumor_social` | Unverified/social claim | "Reddit says a short squeeze is coming." |

### Layer 1: Deterministic Checks

This layer should be cheap, fast, and reproducible.

Recommended checks:

| Check | Method | Output |
|---|---|---|
| Source authority | domain/source lookup table | `source_authority_score` |
| Source type | URL/domain/parser rules | `sec_filing`, `company_ir`, `exchange`, `news`, `blog`, `social` |
| Recency decay | date parsed from result/article | `recency_score` |
| Entity match | ticker, company aliases, CIK, domain relation | `entity_match_score` |
| Numeric consistency | parse numbers/percentages/dates | `numeric_consistency_score` |
| Date sanity | no future filing dates, stale evidence flags | `date_sanity_score` |
| Source duplication | URL canonicalization, title similarity | `duplicate_penalty` |

Suggested source tiers for US equities:

| Tier | Source Type | Base Authority |
|---|---|---:|
| T1 | SEC EDGAR/XBRL, exchange/regulator | 0.95-1.00 |
| T2 | Company IR, official press release, audited report | 0.80-0.95 |
| T3 | Established financial media/data vendors | 0.60-0.85 |
| T4 | Analyst notes, newsletters, blogs | 0.35-0.70 |
| T5 | Reddit, X, forums, low-context aggregators | 0.10-0.45 |

Notes:

- SEC data is not key-based, but production use should respect SEC access policies and include a descriptive `SEC_USER_AGENT`. SEC also provides structured company facts and filings through `data.sec.gov`; see [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
- Company IR is strong for "what the company reported" but can be biased for interpretation.
- Financial media can be useful for breaking news but should be cross-checked against primary sources when the claim is factual.

### Layer 2: Narrow Semantic LLM Judges

Use small, auditable calls. Each call should return constrained JSON, not prose.

Examples:

```json
{
  "task": "evidence_support",
  "question": "Does the evidence support the claim?",
  "allowed_labels": ["supports", "contradicts", "not_enough_info"],
  "score_range": [0, 10]
}
```

Recommended semantic judges:

| Judge | Question | Output |
|---|---|---|
| `judge_argument_type` | What type of claim is this? | label + confidence |
| `judge_evidence_support` | Does evidence support claim? | support label + score |
| `judge_independence` | Are two sources independent? | yes/no + score |
| `judge_context_match` | Same company, date, period, metric? | score |
| `judge_claim_specificity` | Is the claim precise enough to verify? | score |
| `judge_forward_looking_basis` | Is a forecast backed by assumptions/evidence? | score |

Important constraint: the LLM never produces the final score.

### Layer 3: Transparent Aggregation

Aggregation should be deterministic and explainable.

Example high-level formula:

```text
credibility =
  w_authority   * source_authority
+ w_recency     * recency
+ w_relevance   * relevance
+ w_support     * evidence_support
+ w_consistency * numeric_date_consistency
+ w_independent * independent_confirmation
- penalties
```

Weights should vary by argument type:

| Dimension | Metric Fact | Event Fact | Attribution Fact | Opinion Analysis | Forecast |
|---|---:|---:|---:|---:|---:|
| Source authority | 0.25 | 0.20 | 0.25 | 0.10 | 0.10 |
| Recency | 0.10 | 0.20 | 0.15 | 0.10 | 0.10 |
| Evidence support | 0.25 | 0.25 | 0.25 | 0.15 | 0.20 |
| Numeric/date consistency | 0.25 | 0.10 | 0.10 | 0.05 | 0.05 |
| Independence | 0.10 | 0.15 | 0.15 | 0.20 | 0.25 |
| Forecast basis / reasoning | 0.05 | 0.10 | 0.10 | 0.40 | 0.30 |

This table is a good default for MVP. Later, weights can be learned or calibrated, but the first version should be hard-coded for reproducibility.

### Layer 4: Agent-Facing Tools

The toolkit should expose a small set of composable tools:

| Tool | Purpose |
|---|---|
| `classify_financial_argument` | Determine claim type and rubric |
| `search_financial_sources` | Retrieve candidate sources for a ticker/claim |
| `extract_financial_evidence` | Convert pages/results into evidence units |
| `score_source_authority` | Deterministic source tier scoring |
| `check_numeric_consistency` | Compare numbers, dates, periods, units |
| `judge_evidence_support` | Narrow LLM semantic support check |
| `judge_source_independence` | Detect circular reporting/republication |
| `aggregate_credibility_score` | Deterministic weighted final score |
| `build_evidence_pack` | One-call orchestration for external agents |

The main convenience tool should be `build_evidence_pack`.

## 5. Provider-Agnostic Schema Direction

Internal tool definition:

```json
{
  "name": "build_evidence_pack",
  "description": "Build a source-aware credibility assessment for a US equity claim.",
  "input_schema": {
    "type": "object",
    "properties": {
      "claim": {"type": "string"},
      "ticker": {"type": "string"},
      "as_of_date": {"type": "string", "format": "date"},
      "max_sources": {"type": "integer", "default": 8}
    },
    "required": ["claim", "ticker"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "verdict": {
        "type": "string",
        "enum": ["supported", "contradicted", "mixed", "insufficient"]
      },
      "credibility_score": {"type": "number"},
      "argument_type": {"type": "string"},
      "score_breakdown": {"type": "object"},
      "evidence": {"type": "array"},
      "risk_flags": {"type": "array"}
    }
  }
}
```

Adapters:

- OpenAI: wrap as `{"type": "function", "function": ...}`.
- Anthropic: expose `name`, `description`, and `input_schema`.
- Future MCP: expose the same internal tool metadata through an MCP server.

## 6. Output Object

Recommended final output:

```json
{
  "claim": "Apple revenue grew 6% year over year in the latest quarter.",
  "ticker": "AAPL",
  "argument_type": "metric_fact",
  "verdict": "supported",
  "credibility_score": 0.87,
  "score_breakdown": {
    "source_authority": 0.93,
    "recency": 0.82,
    "evidence_support": 0.90,
    "numeric_consistency": 0.88,
    "independence": 0.70,
    "penalties": 0.03
  },
  "evidence": [
    {
      "url": "https://www.sec.gov/...",
      "source_type": "sec_filing",
      "source_tier": "T1",
      "published_at": "2026-05-01",
      "support_label": "supports",
      "support_score": 0.95,
      "summary": "The filing reports revenue for the relevant quarter."
    }
  ],
  "risk_flags": ["single_primary_source"]
}
```

## 7. API Keys and Configuration

Use a local `.env` file for user secrets and do not commit it.

Initial environment variables:

```text
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SERPER_API_KEY=
JINA_API_KEY=
FINNHUB_API_KEY=
SEC_USER_AGENT="your-name your-email@example.com"
```

Notes:

- OpenAI/Anthropic keys are only needed for semantic judge calls.
- Serper/Jina are useful for web search and extraction, but the design should allow callers to pass pre-fetched search results for offline/demo mode.
- SEC EDGAR does not use an API key, but should receive a clear user agent.

## 8. MVP Recommendation

Build the MVP around one core user story:

> Given a US stock ticker and a financial claim, return a transparent credibility verdict with evidence and score breakdown.

MVP tools:

1. `classify_financial_argument`
2. `search_financial_sources`
3. `extract_financial_evidence`
4. `score_source_authority`
5. `judge_evidence_support`
6. `aggregate_credibility_score`
7. `build_evidence_pack`

MVP claim types:

1. `metric_fact`
2. `event_fact`
3. `opinion_analysis`
4. `forecast`

MVP source types:

1. SEC filings/company facts
2. Company IR / press releases
3. Established financial media
4. Analyst/newsletter/blog
5. Social/forum

## 9. Evaluation Can Come Later, But Keep Hooks Now

The code should log intermediate scores from day one so evaluation is easy later.

Possible later evaluation:

- Raw search vs reranked search: compare top-5 source quality.
- Claim verification set: 30-50 manually labeled US equity claims.
- Metrics: top-k authoritative source hit rate, support-label accuracy, contradiction detection, and explanation completeness.
- Ablation: Layer 1 only vs Layer 1 + Layer 2 vs full aggregation.

## 10. Main Risks

1. Circular sourcing: many financial articles repeat the same wire/story.
2. Paywalls: high-quality sources may be inaccessible.
3. Forecasts: credibility should mean "well-supported", not "will be true".
4. Company bias: official sources are authoritative for reported facts, not neutral for interpretation.
5. Latency/cost: semantic judges should be batched and cached.
6. Legal framing: output should be credibility assessment, not investment advice.

## 11. Final Recommendation

Yes, this is a strong final project direction. The most defensible implementation is a glass-box credibility package, not an end-to-end trading advisor.

The colleague's pattern is exactly the right backbone:

- deterministic base scoring,
- narrow LLM semantic checks,
- deterministic aggregation,
- transparent traceability.

The key improvement is to add argument type classification before scoring. In finance, the same source has different meaning depending on whether the claim is a historical fact, attribution, opinion, or forecast.

The first version should be narrow, US-equity-only, provider-agnostic, and independent from the older Clarity codebase. It can still borrow ideas such as tool schemas and search/extraction wrappers, but the new package should have its own clean architecture.

## Sources

- FActScore: [https://arxiv.org/abs/2305.14251](https://arxiv.org/abs/2305.14251)
- SAFE: [https://arxiv.org/abs/2403.18802](https://arxiv.org/abs/2403.18802)
- RAGChecker: [https://arxiv.org/abs/2408.08067](https://arxiv.org/abs/2408.08067)
- RAGAS: [https://arxiv.org/abs/2309.15217](https://arxiv.org/abs/2309.15217)
- ARES: [https://arxiv.org/abs/2311.09476](https://arxiv.org/abs/2311.09476)
- TREC RAG Track: [https://trec-rag.github.io/](https://trec-rag.github.io/)
- OpenAI Structured Outputs: [https://platform.openai.com/docs/guides/structured-outputs](https://platform.openai.com/docs/guides/structured-outputs)
- Anthropic Tool Use: [https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use)
- Model Context Protocol Tools: [https://modelcontextprotocol.io/docs/concepts/tools](https://modelcontextprotocol.io/docs/concepts/tools)
- SEC EDGAR APIs: [https://www.sec.gov/search-filings/edgar-application-programming-interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
