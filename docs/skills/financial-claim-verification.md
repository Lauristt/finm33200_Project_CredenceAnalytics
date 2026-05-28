# Financial Claim Verification Skill

Use this workflow when reviewing an investment memo, analyst note, or financial statement.

1. Extract entities and asset classes.
2. Decompose the memo into atomic factual claims.
3. Route each claim to official or structured sources first.
4. Retrieve evidence and preserve provenance.
5. Convert structured evidence into canonical facts.
6. Verify numeric, logical, and source-quality dimensions.
7. Calibrate uncertainty and human-review flags.
8. Build a report plus trace.
9. Run `audit_verification_chain` before relying on the result.

Default tool profile: `agent_core`.

Use `retrieval_deep` when the claim needs SEC-specific calls, historical prices, benchmark comparison, or vendor fundamentals.

Never turn the result into investment advice.

