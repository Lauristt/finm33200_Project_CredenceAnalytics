# Web Search

Source id: serper_web
Reference docs: https://serper.dev/
Authority tier: T4 supplemental discovery
License tag: unknown

API playbook:
- Auth/env: requires `SERPER_API_KEY`.
- Endpoint: `POST https://google.serper.dev/search`.
- Headers: `X-API-KEY: {SERPER_API_KEY}` and `Content-Type: application/json`.
- Request body: include `q` for the query and usually `num` for result count; keep domain filters or exact quoted phrases in the trace when used.
- Response schema: common fields include `organic[]`, `title`, `link`, `snippet`, `date`, `source`, and optional news/knowledge panels depending on request type.
- Query construction: build queries from the claim, entity, time window, and desired official source; prefer official domains or investor-relations/regulator pages over generic news snippets.
- Adapter output: search results are discovery only. The verifier should fetch/read the destination source before using it as evidence, and web-only support usually requires human review.

Use for:
- Discovery of relevant pages when structured official APIs cannot directly answer the claim.
- Finding official URLs, company investor-relations pages, press releases, or secondary context for follow-up.

Do not use for:
- Primary verification when SEC, FRED, Treasury, GLEIF, or another official structured API can answer the claim.
- Treating news, blogs, social posts, or scraped snippets as authoritative financial evidence.

Important metadata:
- Preserve query, result title, URL, domain, snippet, retrieval time, and whether the destination is official or secondary.
- Use domain/source governance after retrieval; search result rank alone is not evidence quality.
- Treat web-only support as human-review or low-confidence for financial factual claims.

Progressive-disclosure guidance:
- First-pass card should only say this source is supplemental web discovery.
- Load this detail when no structured source is clearly sufficient, or when the task explicitly asks to find external context.
