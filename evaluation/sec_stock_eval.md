# SEC Stock Claim Benchmark

Scope: `evaluation/claims_news.json` rows where `asset_class == "stock"`. Evidence retrieval is restricted to SEC EDGAR Company Facts JSON from `data.sec.gov/api/xbrl/companyfacts`.

Method: each statement is run through the same decomposition and verification path, but candidate evidence is pre-fetched only from SEC Company Facts. `strict` counts only fully supported/verified verdicts as true; `lenient` also counts partial support as true.

## Summary

- Rows: 56
- Strict Accuracy: 8/56 (14.3%)
- Lenient Accuracy: 15/56 (26.8%)
- Sec Retrieval Rate: 47/56 (83.9%)
- Sec Used Rate: 24/56 (42.9%)
- Human Review Rate: 21/56 (37.5%)
- Error Rate: 0/56 (0.0%)

## Diagnostic Takeaways

- SEC retrieval itself is mostly working: 47/56 (83.9%) rows got a Company Facts result, but only 24/56 (42.9%) rows used that SEC evidence in verification.
- The strict verifier currently produces no true/false decisions for this subset: many true rows become `na` (15/26 (57.7%)) or `review`, and false rows mostly become `review` (18/19 (94.7%)).
- Lenient scoring is unsafe right now: 9/19 (47.4%) false rows become `true` because partial lexical support is not capped by numeric exactness.
- Opinion/forecast filtering is partly working: 8/11 (72.7%) `na` rows were correctly skipped under strict scoring.
- Canonical fact extraction is a bottleneck: 32/56 (57.1%) rows ended with zero canonical SEC facts after retrieval.
- Top review reasons: ambiguous_unit_currency_or_period=20, low_retrieval_sufficiency=14, no_official_primary_source=14, low_entity_resolution_confidence=8.

## Highest-Priority Fixes

- Split mixed claims such as `reported revenue X, beating estimates Y`: SEC can verify the reported company metric, while analyst estimate comparisons need a separate estimates/news source or should be marked human review.
- Strengthen SEC concept mapping for `adjusted EPS`, segment revenue, geography/product revenue, cloud/AWS/data-center revenue, and bank net-interest-income concepts.
- Require numeric derivation for numeric SEC claims before returning supported/partially supported; otherwise cap the verdict at review/insufficient.
- Keep forecast/opinion/causal explanation claims out of fact-check unless the sentence contains a concrete, SEC-verifiable metric.
- Treat `used SEC evidence` separately from `retrieved SEC evidence`; retrieval alone should not count as coverage.

## Label Distribution

- true: 26
- false: 19
- na: 11

## Claim Type Distribution

- numeric: 40
- forecast: 6
- opinion: 5
- causal: 4
- factual: 1

## Strict Confusion Matrix

| Expected | true | false | na | review | error |
|---|---:|---:|---:|---:|---:|
| true | 0 | 0 | 15 | 11 | 0 |
| false | 0 | 0 | 1 | 18 | 0 |
| na | 0 | 0 | 8 | 3 | 0 |

## Lenient Confusion Matrix

| Expected | true | false | na | review | error |
|---|---:|---:|---:|---:|---:|
| true | 7 | 0 | 15 | 4 | 0 |
| false | 9 | 0 | 1 | 9 | 0 |
| na | 2 | 0 | 8 | 1 | 0 |

## Mismatches And Review Rows

- `S1` `NVDA` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Nvidia reported first-quarter revenue of $81.62 billion, beating analyst estimates of $79.18 billion.
- `S1n` `NVDA` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Nvidia reported first-quarter revenue of $61.62 billion.
- `S2` `NVDA` label=true strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Nvidia's data center revenue rose 92% year over year in the first quarter.
- `S2n` `NVDA` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Nvidia's data center revenue rose 19% year over year in the first quarter.
- `S9` `NVDA` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Nvidia posted adjusted earnings of $1.87 per share, beating estimates of $1.77.
- `S9n` `NVDA` label=false strict=review lenient=review sec=0/1 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: Nvidia posted adjusted earnings of $2.87 per share.
- `S6` `NVDA` label=na strict=review lenient=review sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=ambiguous_unit_currency_or_period|low_retrieval_sufficiency|no_official_primary_source. Claim: Nvidia guided to second-quarter revenue of between $89.1 billion and $92.8 billion.
- `Sc1` `NVDA` label=true strict=na lenient=na sec=0/0 facts=no canonical facts; reason=n/a. Claim: Nvidia's growth was driven by surging data center demand.
- `S3` `AAPL` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Apple reported second-quarter revenue of $111.2 billion, above estimates of $109.66 billion.
- `S3d` `AAPL` label=false strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Apple reported fourth-quarter revenue of $111.2 billion, above estimates.
- `S4` `AAPL` label=true strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=ambiguous_unit_currency_or_period. Claim: Apple's Greater China revenue was $20.50 billion in the second quarter.
- `S4n` `AAPL` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=ambiguous_unit_currency_or_period. Claim: Apple's Greater China revenue was $30.50 billion in the second quarter.
- `S5` `AAPL` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Apple posted adjusted earnings per share of $2.01, beating estimates of $1.96.
- `S8` `AAPL` label=true strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=ambiguous_unit_currency_or_period. Claim: Apple's iPhone revenue was $56.99 billion in the second quarter.
- `S8n` `AAPL` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=ambiguous_unit_currency_or_period. Claim: Apple's iPhone revenue was $46.99 billion in the second quarter.
- `Sc2` `AAPL` label=true strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=n/a. Claim: Apple's revenue beat was driven by strong iPhone and China sales.
- `MS1` `MSFT` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Microsoft reported adjusted earnings per share of $4.27, beating consensus by $0.21.
- `MS1n` `MSFT` label=false strict=review lenient=review sec=0/1 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: Microsoft reported adjusted earnings per share of $3.27.
- `MS2` `MSFT` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Microsoft reported revenue of $82.89 billion, beating estimates by about $1.5 billion.
- `MS2n` `MSFT` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=ambiguous_unit_currency_or_period. Claim: Microsoft reported revenue of $92.89 billion.
- `MS3` `MSFT` label=na strict=review lenient=true sec=1/1 facts=DeferredRevenueCurrent|RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueNet; reason=ambiguous_unit_currency_or_period. Claim: Microsoft guided to Azure revenue growth of 39% to 40% for the current quarter.
- `MSc` `MSFT` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Microsoft's revenue grew because of strong Azure and cloud demand.
- `AM1` `AMZN` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Amazon reported earnings per share of $2.78, beating estimates by $1.10.
- `AM1n` `AMZN` label=false strict=review lenient=review sec=0/1 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: Amazon reported earnings per share of $1.78.
- `AM2` `AMZN` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Amazon reported revenue of $181.5 billion, beating estimates by over $4 billion.
- `AM2n` `AMZN` label=false strict=review lenient=review sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|SalesRevenueNet; reason=ambiguous_unit_currency_or_period|low_retrieval_sufficiency|no_official_primary_source. Claim: Amazon reported revenue of $151.5 billion.
- `AM3` `AMZN` label=true strict=review lenient=review sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|SalesRevenueNet|SalesRevenueServicesNet; reason=ambiguous_unit_currency_or_period|low_retrieval_sufficiency|no_official_primary_source. Claim: Amazon Web Services revenue rose 24% to $35.6 billion in the fourth quarter of 2025.
- `AM3d` `AMZN` label=false strict=review lenient=review sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|SalesRevenueNet|SalesRevenueServicesNet; reason=ambiguous_unit_currency_or_period|low_retrieval_sufficiency|no_official_primary_source. Claim: Amazon Web Services revenue rose 24% to $35.6 billion in the first quarter of 2025.
- `GO1` `GOOGL` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Alphabet reported adjusted earnings per share of $2.62, missing estimates by a penny.
- `GO1d` `GOOGL` label=false strict=review lenient=review sec=0/1 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: Alphabet reported fourth-quarter adjusted earnings per share of $2.62.
- `GO2` `GOOGL` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Alphabet reported revenue of nearly $110 billion, beating estimates by $2.7 billion.
- `GO2n` `GOOGL` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Alphabet reported revenue of nearly $140 billion.
- `GO3` `GOOGL` label=true strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Google Cloud revenue soared 63% year over year.
- `GO3n` `GOOGL` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Google Cloud revenue soared 33% year over year.
- `TS1` `TSLA` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Tesla posted first-quarter revenue of $22.39 billion, topping the consensus estimate of $21.92 billion.
- `TS1n` `TSLA` label=false strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues; reason=n/a. Claim: Tesla posted first-quarter revenue of $32.39 billion.
- `TS2` `TSLA` label=true strict=review lenient=review sec=0/1 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: Tesla reported first-quarter adjusted earnings of 41 cents per share.
- `TS2n` `TSLA` label=false strict=review lenient=review sec=0/1 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: Tesla reported first-quarter adjusted earnings of 81 cents per share.
- `TS3` `TSLA` label=true strict=review lenient=true sec=1/1 facts=RevenueFromContractWithCustomerExcludingAssessedTax|Revenues|SalesRevenueEnergyServices|SalesRevenueServicesNet; reason=explanation_claim_needs_human_review. Claim: Tesla's services and other revenue climbed to $3.75 billion from $2.64 billion a year earlier.
- `TS4` `TSLA` label=na strict=review lenient=true sec=1/1 facts=CashAndCashEquivalentsAtCarryingValue|NetCashProvidedByUsedInOperatingActivities|PaymentsToAcquirePropertyPlantAndEquipment; reason=n/a. Claim: Tesla expects 2026 capital expenditure of over $25 billion and negative free cash flow for the rest of the year.
- `ME1` `META` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Meta's first-quarter revenue beat was driven by strength in advertising.
- `ME2` `META` label=true strict=na lenient=na sec=0/1 facts=no canonical facts; reason=n/a. Claim: Meta's CFO said the company will fund its AI ambitions primarily with cash rather than debt.
- `JP1` `JPM` label=true strict=review lenient=review sec=1/1 facts=NetIncomeLoss; reason=ambiguous_unit_currency_or_period|low_retrieval_sufficiency|no_official_primary_source. Claim: JPMorgan generated fourth-quarter net income of $14.7 billion excluding a significant item.
- `JP1n` `JPM` label=false strict=review lenient=review sec=1/1 facts=NetIncomeLoss; reason=ambiguous_unit_currency_or_period|low_retrieval_sufficiency|no_official_primary_source. Claim: JPMorgan generated fourth-quarter net income of $24.7 billion.
- `JP2` `JPM` label=true strict=review lenient=true sec=1/1 facts=NewAccountingPronouncementOrChangeInAccountingPrincipleEffectOfChangeOnNetRevenue|Revenues; reason=n/a. Claim: JPMorgan reported fourth-quarter net revenue of $46.8 billion, up 7%.
- `JP2n` `JPM` label=false strict=review lenient=true sec=1/1 facts=NewAccountingPronouncementOrChangeInAccountingPrincipleEffectOfChangeOnNetRevenue|Revenues; reason=n/a. Claim: JPMorgan reported fourth-quarter net revenue of $66.8 billion.
- `JP3` `JPM` label=true strict=review lenient=review sec=0/0 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: JPMorgan reported net interest income of $25.1 billion in the fourth quarter, up 7%.
- `JP3n` `JPM` label=false strict=review lenient=review sec=0/0 facts=no canonical facts; reason=ambiguous_unit_currency_or_period|low_entity_resolution_confidence|low_retrieval_sufficiency|no_official_primary_source. Claim: JPMorgan reported net interest income of $15.1 billion in the fourth quarter.

## Per-Entity SEC Coverage

- AAPL: strict 0/8 (0.0%); SEC used 5/8 (62.5%)
- AMZN: strict 2/8 (25.0%); SEC used 3/8 (37.5%)
- GOOGL: strict 1/7 (14.3%); SEC used 3/7 (42.9%)
- JPM: strict 0/6 (0.0%); SEC used 4/6 (66.7%)
- META: strict 1/3 (33.3%); SEC used 0/3 (0.0%)
- MSFT: strict 1/7 (14.3%); SEC used 2/7 (28.6%)
- NVDA: strict 1/9 (11.1%); SEC used 4/9 (44.4%)
- TSLA: strict 2/8 (25.0%); SEC used 3/8 (37.5%)
