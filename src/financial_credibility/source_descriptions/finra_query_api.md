# FINRA Query API

Source id: finra_query_api
Official docs: https://developer.finra.org/products/query-api
Developer docs: https://developer.finra.org/docs
Authority tier: T1 official/regulatory source
License tag: third_party_restricted
Adapter status: planned

Official description summary:
- FINRA's Query API provides a standard query interface for data categories such as Equity, Fixed Income, and Registration.
- It supports many datasets through common request structures, filtering, synchronous and asynchronous requests.
- API Console access/onboarding may be required depending on use case and organization.

Use for:
- FINRA regulatory datasets, fixed-income or TRACE-related checks, registration checks, and filtered large dataset retrieval.
- Claims where FINRA is the regulator/source of record.

Do not use for:
- Company-reported financial statement facts.
- Macro observations, Treasury fiscal data, or market-data claims that require exchange licensing.

Important metadata:
- Preserve dataset group, dataset name, dataset version, filters, fields, request method, async job ID if any, response timestamp, and FINRA access scope.
- Treat onboarding limits, mock API explorer results, dataset-specific terms, and missing active dataset status as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say FINRA Query API covers FINRA regulatory datasets through a standard interface.
- Load this detail for FINRA, TRACE, registration, fixed-income regulatory, short interest, or broker-dealer dataset claims.

