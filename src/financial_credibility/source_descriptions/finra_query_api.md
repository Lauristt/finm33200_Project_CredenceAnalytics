# FINRA Query API

Source id: finra_query_api
Official docs: https://developer.finra.org/products/query-api
Developer docs: https://developer.finra.org/docs
Authority tier: T1 official/regulatory source
License tag: third_party_restricted
Adapter status: implemented

Official description summary:
- FINRA's Query API provides a standard query interface for data categories such as Equity, Fixed Income, and Registration.
- It supports many datasets through common request structures, filtering, synchronous and asynchronous requests.
- API Console access/onboarding may be required depending on use case and organization.

API playbook:
- Auth/env: requires `FINRA_CLIENT_ID` and `FINRA_CLIENT_SECRET`.
- Token endpoint: `POST https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token` with form body `grant_type=client_credentials` and Basic auth built from `client_id:client_secret`.
- Data endpoint pattern: `GET https://api.finra.org/data/group/{group}/name/{dataset}`.
- Current params: `limit` capped at 100 and optional `asOfDate=YYYY-MM-DD`. Future filters should be passed according to each dataset's Query API schema.
- Starter mappings: TRACE/fixed income routes map to `fixedIncomeMarket/corporateMarketBreadth`; Treasury aggregate claims to `fixedIncomeMarket/treasuryDailyAggregates`; other starter datasets include `agencyMarketBreadth`, `corporate144AMarketBreadth`, and `corporateMarketSentiment`.
- Response schema: dataset rows vary by group/name. Current summarizer looks for dates such as `tradeReportDate`, `tradeDate`, `reportDate`, `asOfDate` and fields such as `totalTrades`, `totalVolume`, `advances`, `declines`, and dealer/ATS volumes.
- Adapter output: return rows plus entitlement diagnostics. HTTP 401/403 means credential or dataset entitlement problem, not claim contradiction.

Use for:
- FINRA regulatory datasets, fixed-income or TRACE-related checks, registration checks, and filtered large dataset retrieval.
- Claims where FINRA is the regulator/source of record.
- Runtime starter adapter targets Query API fixed-income market breadth/sentiment and Treasury aggregate datasets through OAuth2 client credentials.

Do not use for:
- Company-reported financial statement facts.
- Macro observations, Treasury fiscal data, or market-data claims that require exchange licensing.

Important metadata:
- Preserve dataset group, dataset name, dataset version, filters, fields, request method, async job ID if any, response timestamp, and FINRA access scope.
- Treat onboarding limits, mock API explorer results, dataset-specific terms, and missing active dataset status as human-review triggers.
- Preserve OAuth mode without logging client secrets or bearer tokens.

Progressive-disclosure guidance:
- First-pass card should only say FINRA Query API covers FINRA regulatory datasets through a standard interface.
- Load this detail for FINRA, TRACE, registration, fixed-income regulatory, short interest, or broker-dealer dataset claims.
