# XBRL US API

Source id: xbrl_us_api
Official docs: https://xbrl.us/home/priorities/use/xbrl-api/
Sample queries: https://xbrl.us/home/priorities/use/xbrl-api/sample-api-queries/
Authority tier: T2 official-adjacent structured XBRL enhancement layer
License tag: third_party_restricted
Adapter status: planned

Official description summary:
- XBRL US provides an API over its Public Filings Database and XBRL filed data.
- The API is useful for querying reports, facts, taxonomy metadata, dimensions, and filing attributes from SEC and FERC XBRL filings.
- It should be treated as an enhanced access layer over filings, not as a replacement for preserving original SEC/FERC provenance.

API playbook:
- Auth/env: XBRL US access is credentialed/licensed. Add explicit env vars before production use, for example `XBRL_US_API_KEY` or the provider-approved auth pair required by the account.
- Discovery endpoints: use XBRL US API docs/sample queries to identify report/fact endpoints for the relevant filing universe; keep report/fact query params in the trace.
- Query shape: start from entity identifiers such as CIK/ticker plus concept/taxonomy hints, then constrain by form, fiscal period, filing date, and dimensions.
- Response schema: preserve report identifiers, entity identifiers, concept, taxonomy, unit, period, value, dimensions, accession/report URL, and filing metadata.
- Naming rules: only use after SEC Company Facts is insufficient, especially when the claim needs dimensions, taxonomy relationships, or FERC filings.
- Adapter output: this source should return provenance-rich fact rows and the original filing URL; never present XBRL US rows as primary SEC evidence without SEC/FERC provenance.

Use for:
- High-granularity XBRL fact search when SEC Company Facts is too coarse.
- Cross-company comparisons that need dimensions, taxonomy metadata, report IDs, accession numbers, or period metadata.
- FERC utility filing checks.

Do not use for:
- Primary evidence when direct SEC data is sufficient and cleaner.
- Macro, labor, Treasury fiscal, or market-price claims.
- Legal-entity identity resolution.

Important metadata:
- Preserve report ID, entity name, ticker, CIK, accession, filing date, accepted timestamp, document type, concept local name, taxonomy, dimensions, period, unit, value, and SEC URL.
- Treat XBRL US as a provenance-preserving query layer: final reports should still point back to the original filing where possible.
- API authentication, access tier, and reuse terms must be tracked before production use.

Progressive-disclosure guidance:
- First-pass card should only say this source is a taxonomy-aware XBRL fact API over public filings.
- Load this detail when a claim asks for dimensional XBRL, taxonomy-aware comparisons, FERC filings, or SEC facts not exposed cleanly by Company Facts.
