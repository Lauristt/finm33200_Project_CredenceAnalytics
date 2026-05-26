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

