# Arelle XBRL Parser

Source id: arelle
Official docs: https://arelle.readthedocs.io/
Repository: https://github.com/Arelle/Arelle
Authority tier: T2 parser/validator component
License tag: unknown
Adapter status: planned_parser

Official description summary:
- Arelle is an end-to-end open-source XBRL platform with GUI, command-line, web service, and Python API modes.
- It supports XBRL, Inline XBRL, XBRL dimensions, formula validation, taxonomy packages, and multiple filing-program validation rule sets.
- It is a processing and validation component, not an external evidence source by itself.

API playbook:
- Auth/env: no external API key. This is a local parser/service dependency; record the installed Arelle version.
- Input forms: SEC filing HTML/iXBRL URL, local downloaded filing, taxonomy package, or XBRL instance/document set.
- CLI pattern: run Arelle with entrypoint filing URL/path plus validation/extraction options; preserve command, taxonomy package, and generated output path in the trace.
- Python/service pattern: load the filing into an Arelle controller/model manager, inspect facts, contexts, units, dimensions, and validation messages.
- Response/schema to normalize: fact concept QName, value, decimals/precision, unit, context period, dimensions, source locator, and validation status.
- Adapter status: planned parser. Do not advertise this as a remote retrieval source until dependency installation, parser invocation, and result normalization are wired into runtime.
- Adapter output: should return filing-derived facts with original SEC/FERC provenance and validation diagnostics; parser errors should become human-review evidence, not contradictions.

Use for:
- Local parsing of SEC iXBRL/HTML filings when Company Facts lacks the exact fact or table context.
- Taxonomy-aware validation, dimensional facts, calculation checks, and Inline XBRL extraction.
- Human-review workflows where a filing needs an inspectable XBRL/iXBRL view.

Do not use for:
- Fetching external data by itself.
- Macro statistics, legal entity identifiers, market prices, or media claims.
- Replacing provenance from the original filing URL, accession number, and SEC source.

Important metadata:
- Preserve filing URL or local file hash, parser version, taxonomy package, validation messages, fact concept, context, unit, period, decimals, dimensions, source locator, and extraction timestamp.
- Treat validation errors, extension taxonomy ambiguity, and conflicting duplicate facts as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say Arelle parses and validates XBRL/iXBRL filings locally.
- Load this detail when the claim requires filing-level parsing, iXBRL extraction, taxonomy validation, or dimensional facts.
