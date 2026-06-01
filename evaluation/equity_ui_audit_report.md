# Equity UI Audit Loop

Samples: 10
Findings: 34

## Finding Summary

- major: 34

## Categories

- built_in:coverage: 15
- missing_retrieval: 8
- numeric: 6
- built_in:source_alignment: 3
- built_in:tool_use: 2

## Per Sample

### eq_ap_indexes_2026_05_26

- Source: [AP News](https://apnews.com/article/wall-street-stocks-dow-nasdaq-b2fb9ef30834ed73768f2afd65ec7de0)
- Entities: SPX, NDQ, DJIA, RUT; claims: 8; review: 6; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_ap_indexes_2026_05_26.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_1`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_2`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:tool_use**: Completed report has no recorded retrieval or end-to-end evidence-pack tool call. Affected: `agent_5a5e4becd363`. Recommendation: Ensure retrieval or build_evidence_pack is present in every fact-checking trace.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `RUT:claim_1`. Recommendation: Try the historical_prices adapter with a claim-specific time window.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `RUT:claim_2`. Recommendation: Try the historical_prices adapter with a claim-specific time window.

### eq_ap_indexes_2026_05_27

- Source: [AP News](https://apnews.com/article/wall-street-stocks-dow-nasdaq-6b22ac4e7e8ab54dde3d3499e6643f28)
- Entities: SPX, NDQ, DJIA, RUT; claims: 6; review: 5; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_ap_indexes_2026_05_27.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_1`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:tool_use**: Completed report has no recorded retrieval or end-to-end evidence-pack tool call. Affected: `agent_969f399dda31`. Recommendation: Ensure retrieval or build_evidence_pack is present in every fact-checking trace.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `RUT:claim_1`. Recommendation: Try the historical_prices adapter with a claim-specific time window.

### eq_ap_single_names_2026_05_28

- Source: [AP News](https://apnews.com/article/stocks-markets-oil-iran-trump-inflation-559e1f1e5269976ea21bb551e916c941)
- Entities: SNOW, DLTR, KSS, BBY, HRL, MRVL, SPX; claims: 7; review: 5; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_ap_single_names_2026_05_28.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_1`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `SNOW:claim_1`. Recommendation: Try the historical_prices adapter with a claim-specific time window.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `DLTR:claim_1`. Recommendation: Try the historical_prices adapter with a claim-specific time window.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `KSS:claim_1`. Recommendation: Try the historical_prices adapter with a claim-specific time window.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `BBY:claim_1`. Recommendation: Try the historical_prices adapter with a claim-specific time window.

### eq_nvda_q1_fy2027

- Source: [NVIDIA / GlobeNewswire](https://www.globenewswire.com/news-release/2026/05/20/3298888/0/en/nvidia-announces-financial-results-for-first-quarter-fiscal-2027.html)
- Entities: NVDA; claims: 5; review: 4; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_nvda_q1_fy2027.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_2`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_3`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_4`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.

### eq_aapl_q2_fy2026

- Source: [MacRumors summary of Apple results](https://www.macrumors.com/2026/04/30/apple-2q-2026-earnings/)
- Entities: AAPL; claims: 5; review: 4; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_aapl_q2_fy2026.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_5`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / numeric**: Numeric claim received a positive verdict without a deterministic numeric derivation. Affected: `AAPL:claim_2`. Recommendation: Require a replayable numeric check for numeric claims before returning support.
- **major / numeric**: Numeric claim received a positive verdict without a deterministic numeric derivation. Affected: `AAPL:claim_4`. Recommendation: Require a replayable numeric check for numeric claims before returning support.
- **major / missing_retrieval**: Obvious price or return claim ended with no evidence. Affected: `AAPL:claim_5`. Recommendation: Try the historical_prices adapter with a claim-specific time window.

### eq_msft_q3_fy2026

- Source: [Microsoft Investor Relations](https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast)
- Entities: MSFT; claims: 3; review: 3; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_msft_q3_fy2026.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_2`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / numeric**: Numeric claim received a positive verdict without a deterministic numeric derivation. Affected: `MSFT:claim_1`. Recommendation: Require a replayable numeric check for numeric claims before returning support.
- **major / numeric**: Numeric claim received a positive verdict without a deterministic numeric derivation. Affected: `MSFT:claim_3`. Recommendation: Require a replayable numeric check for numeric claims before returning support.

### eq_amzn_q1_2026

- Source: [Amazon Investor Relations](https://s2.q4cdn.com/299287126/files/doc_earnings/2026/q1/earnings-result/AMZN-Q1-2026-Earnings-Release.pdf)
- Entities: AMZN; claims: 4; review: 4; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_amzn_q1_2026.md`
- **major / built_in:source_alignment**: Displayed evidence appears topically unrelated to the claim. Affected: `claim_1`. Recommendation: Do not attach this source to the claim; rerun source selection with asset class + claim property, or mark the claim for human review.
- **major / built_in:source_alignment**: Displayed evidence appears topically unrelated to the claim. Affected: `claim_2`. Recommendation: Do not attach this source to the claim; rerun source selection with asset class + claim property, or mark the claim for human review.
- **major / built_in:source_alignment**: Displayed evidence appears topically unrelated to the claim. Affected: `claim_3`. Recommendation: Do not attach this source to the claim; rerun source selection with asset class + claim property, or mark the claim for human review.
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_4`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.

### eq_googl_q1_2026

- Source: [Alphabet Investor Relations](https://s206.q4cdn.com/479360582/files/doc_financials/2026/q1/2026q1-alphabet-earnings-release.pdf)
- Entities: GOOGL; claims: 3; review: 2; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_googl_q1_2026.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_3`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / numeric**: Numeric claim received a positive verdict without a deterministic numeric derivation. Affected: `GOOGL:claim_2`. Recommendation: Require a replayable numeric check for numeric claims before returning support.

### eq_tsla_q1_2026

- Source: [TIKR / market coverage](https://www.tikr.com/blog/tesla-q1-2026-earnings-revenue-up-16-eps-up-52-but-free-cash-flow-turns-negative)
- Entities: TSLA; claims: 4; review: 2; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_tsla_q1_2026.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_3`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.

### eq_jpm_q1_2026

- Source: [JPMorgan Chase Investor Relations](https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/quarterly-earnings/2026/1st-quarter/a5fd2d13-877b-43b2-8b58-81bad4399c87.pdf)
- Entities: JPM; claims: 4; review: 4; termination: no_provider_fallback
- Output: `evaluation/equity_ui_audit_outputs/eq_jpm_q1_2026.md`
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_2`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_3`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / built_in:coverage**: Selected sources produced no displayable evidence for this claim. Affected: `claim_4`. Recommendation: Keep the human-review flag, and either add a compatible source/adapter or leave the claim unresolved instead of forcing a verdict.
- **major / numeric**: Numeric claim received a positive verdict without a deterministic numeric derivation. Affected: `JPM:claim_1`. Recommendation: Require a replayable numeric check for numeric claims before returning support.

## Suggested Next Fixes

- Harden routing so equity price/index move claims always call `historical_prices` with the inferred time window.
- Add a numeric-verdict gate: positive numeric verdicts require a replayable derivation.