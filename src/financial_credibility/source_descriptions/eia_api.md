# EIA Open Data API

Source id: eia_api
Official docs: https://www.eia.gov/opendata/documentation.php
API registration: https://www.eia.gov/opendata/register.php
Authority tier: T1 official primary
License tag: public_official
Adapter status: implemented

Official description summary:
- The U.S. Energy Information Administration publishes official energy statistics through APIv2.
- APIv2 exposes hierarchical routes for petroleum, natural gas, electricity, coal, international, and energy-balance datasets.
- API access generally uses an EIA API key; bulk downloads may be available separately.

API playbook:
- Auth/env: requires `EIA_API_KEY` for APIv2 queries.
- Current endpoint pattern: `GET https://api.eia.gov/v2/{route}/data/`.
- Current params: `api_key`, `frequency=daily`, `data[0]=value`, `facets[series][]={series_id}`, `sort[0][column]=period`, `sort[0][direction]=desc`, `offset=0`, `length=5`, and optional `end=YYYY-MM-DD`.
- Starter mappings: Brent `petroleum/pri/spt` + `RBRTE`; WTI `petroleum/pri/spt` + `RWTC`; crude stocks `petroleum/stoc/wstk` + `WCESTUS1`; Henry Hub natural gas `natural-gas/pri/fut` + `RNGWHHD`; gasoline `petroleum/pri/gnd` + `EMM_EPMR_PTE_NUS_DPG`.
- Response schema: `response.data[]` rows with `period`, `value`, `series`, `units`, and route-specific dimensions.
- Time alignment: set `end` from article context for old commodity news; compare daily vs weekly series only when the claim period matches.
- Adapter output: return route, series ID, units, and latest aligned rows. Use FRED only as a supplemental mirror when EIA direct data is unavailable.

Use for:
- WTI, Brent, petroleum spot prices, gasoline, natural gas, inventories, production, consumption, and energy-balance claims.
- Claims where EIA is the primary publisher for an energy statistic.

Do not use for:
- Company filings, labor statistics, national accounts, or security identifiers.
- Licensed exchange/futures prices where an exchange or market-data vendor is the actual source of record.

Important metadata:
- Preserve route, frequency, series/facet, period, value, unit, sort, offset/length, and EIA API request URL.
- Treat route/facet ambiguity, unit differences, weekly versus daily observations, and API revision timing as human-review triggers.

Progressive-disclosure guidance:
- First-pass card should only say EIA covers official energy statistics through APIv2.
- Load this detail for EIA, WTI, Brent, crude oil, petroleum, natural gas, gasoline, inventory, or energy-balance claims.
