# ESMA Registers

Source id: esma_registers
Official docs: https://www.esma.europa.eu/publications-and-data/databases-and-registers
A2A help: https://registers.esma.europa.eu/publication/helpApp
Authority tier: T1 official regulatory source
License tag: public_official
Adapter status: planned

Official description summary:
- ESMA provides registers and financial-market datasets based on notifications, NCA data, and ESMA supervisory activities.
- ESMA Registers expose machine-to-machine services for retrieval of register data maintained by ESMA.
- Register data is maintained through Solr indexes and covers several EU regulatory regimes.

API playbook:
- Auth/env: public register access generally has no API key, but each register may have its own terms and rate behavior.
- Discovery endpoint: start from ESMA register pages/A2A help to identify the register name, Solr core/index, supported fields, and update cadence.
- Query shape: send Solr-style query parameters (`q`, `fq`, `rows`, `start`, `fl`, sorting) against the appropriate register endpoint.
- Response/schema to normalize: register name, entity/product identifier, legal name, jurisdiction, status, authorization date, NCA/source, update timestamp, and returned field list.
- Naming rules: do not reuse one ESMA register schema for another; MiFID, UCITS, AIFMD, benchmarks, sanctions, and positions have different fields.
- Adapter status: planned. Candidate source selection may surface ESMA, but runtime should not claim verification until a register-specific adapter is implemented.
- Adapter output: should return register rows plus field/schema metadata and mark ambiguous Solr hits for human review.

Use for:
- EU regulatory registration, MiFID, UCITS, AIFMD, benchmark, sanction, product/register, and market-venue checks.
- Claims where ESMA register status or EU regulatory dataset membership is the evidence.

Do not use for:
- US company financial statements, US macro data, or general market-price checks.

Important metadata:
- Preserve register/index name, Solr query, fields returned, entity/product identifiers, status, jurisdiction, update timestamp if available, and ESMA URL.
- Treat Solr query ambiguity, register-specific schema differences, and stale index dates as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say ESMA Registers cover EU financial-market regulatory registers.
- Load this detail for ESMA, MiFID, UCITS, AIFMD, EU benchmark, sanctions, or register-status claims.
