import unittest
from datetime import date
from unittest.mock import patch

from financial_credibility import FinancialCredibilityToolkit
from financial_credibility.claims import decompose_claims
from financial_credibility.config import ToolkitConfig
from financial_credibility.claim_verification import verify_atomic_claims
from financial_credibility.derivations import derive_numeric_check
from financial_credibility.facts import canonicalize_evidence, canonicalize_search_results
from financial_credibility.models import (
    Evidence,
    EntityResolution,
    SearchResult,
    SourceTier,
    SourceType,
    VerificationCheck,
    VerificationVerdict,
    to_plain,
)
from financial_credibility.price_history import PricePoint
from financial_credibility.routing import route_sources
from financial_credibility.sources import assess_source
from financial_credibility.tool_registry import all_registered_tools
from financial_credibility.tool_runtime import execute_tool


class OfficialVerifierUpgradeTests(unittest.TestCase):
    def test_source_governance_marks_sec_primary_and_yahoo_supplemental(self):
        sec = assess_source("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")
        yahoo = assess_source("https://query1.finance.yahoo.com/v8/finance/chart/AAPL")

        self.assertTrue(sec.is_official_primary)
        self.assertEqual(sec.license_tag.value, "public_official")
        self.assertFalse(yahoo.is_official_primary)
        self.assertEqual(yahoo.license_tag.value, "third_party_restricted")

    def test_claim_decomposition_and_routing(self):
        claims = decompose_claims(
            "Apple revenue grew 6% year over year; operating cash flow improved mainly from working capital release."
        )

        self.assertEqual(len(claims), 2)
        self.assertEqual(route_sources(claims[0])["routes"][:2], ["sec_company_facts", "sec_recent_filings"])

    def test_claim_decomposition_carries_market_section_time_context(self):
        claims = decompose_claims(
            "On Tuesday:\n\n"
            "The S&P 500 rose 45.65 points, or 0.6%, to 7,519.12.\n\n"
            "For the year:\n\n"
            "The S&P 500 is up 673.62 points, or 9.8%."
        )
        texts = [claim.text for claim in claims]

        self.assertIn("On Tuesday, The S&P 500 rose 45.65 points, or 0.6%, to 7,519.12", texts)
        self.assertIn("For the year, The S&P 500 is up 673.62 points, or 9.8%", texts)

    def test_claim_decomposition_carries_inline_market_time_context(self):
        claims = decompose_claims(
            "The S&P 500 added 0.6% Tuesday after trading resumed following Monday's holiday. "
            "The Nasdaq composite climbed 1.2%. "
            "The Dow Jones Industrial Average slipped 0.2%."
        )
        texts = [claim.text for claim in claims]

        self.assertIn("The S&P 500 added 0.6% Tuesday after trading resumed following Monday's holiday", texts)
        self.assertIn("On Tuesday, The Nasdaq composite climbed 1.2%", texts)
        self.assertIn("On Tuesday, The Dow Jones Industrial Average slipped 0.2%", texts)

    def test_canonicalizes_sec_company_facts_fixture(self):
        results = [
            SearchResult(
                title="SEC Company Facts for AAPL",
                url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                snippet=(
                    "Revenues (USD) 2024 Q4: 94930000000 filed 2024-11-01 form 10-K; "
                    "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K"
                ),
                published_at="2025-10-31",
                source="SEC EDGAR",
                raw={"provider": "sec_company_facts", "cik": 320193},
            )
        ]

        facts = canonicalize_search_results(results, "AAPL")

        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0].authority_tier.value, "T1")
        self.assertEqual(facts[0].currency, "USD")
        self.assertEqual(facts[0].cik, "0000320193")

    def test_canonicalizes_current_sec_period_excerpt_without_date_fake_fact(self):
        source = assess_source("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")
        facts = canonicalize_evidence(
            [
                Evidence(
                    url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    title="SEC Company Facts for AAPL",
                    text=(
                        "RevenueFromContractWithCustomerExcludingAssessedTax (USD) "
                        "for fiscal quarter ending 2026-03-28: 111184000000 (form 10-Q); "
                        "RevenueFromContractWithCustomerExcludingAssessedTax (USD) "
                        "for fiscal year ending 2025-09-27: 416161000000 (form 10-K)"
                    ),
                    source_type=source.source_type,
                    source_tier=source.source_tier,
                    domain=source.domain,
                    published_at="2026-05-01",
                    license_tag=source.license_tag,
                    is_official_primary=True,
                )
            ],
            "AAPL",
        )

        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0].fact_name, "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual(facts[0].value, 111184000000)
        self.assertEqual(facts[0].report_period, "2026-03-28")
        self.assertNotIn("SEC Company Facts for AAPL", {fact.fact_name for fact in facts})
        self.assertNotIn(2026, {fact.value for fact in facts})

    def test_acquisition_claim_does_not_treat_eps_as_relevant_fact(self):
        source = assess_source("https://data.sec.gov/api/xbrl/companyfacts/CIK0000475520.json")
        evidence = [
            Evidence(
                url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000475520.json",
                title="SEC Company Facts for JEF",
                text=(
                    "EarningsPerShareDiluted (USD/shares) for fiscal quarter ending "
                    "2026-02-28: 0.7 (form 10-Q)"
                ),
                source_type=source.source_type,
                source_tier=source.source_tier,
                domain=source.domain,
                published_at="2026-04-07",
                license_tag=source.license_tag,
                is_official_primary=True,
            )
        ]
        facts = canonicalize_evidence(evidence, "JEF")

        results = verify_atomic_claims(
            "SMBC acquired Jefferies in 2026.",
            evidence,
            facts,
            EntityResolution(ticker="JEF", entity_id="JEF", confidence=0.80),
        )

        self.assertEqual(results[0].verdict, VerificationVerdict.INSUFFICIENT)
        self.assertEqual(results[0].canonical_fact_ids, [])
        self.assertEqual(results[0].evidence_urls, [])

    def test_evidence_pack_contains_atomic_claims_facts_and_audit_trace(self):
        toolkit = FinancialCredibilityToolkit(ToolkitConfig())
        pack = toolkit.build_evidence_pack(
            claim=(
                "Apple revenue grew 6% year over year; "
                "operating cash flow improved mainly from working capital release."
            ),
            ticker="AAPL",
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "SEC Company Facts for AAPL",
                    "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "snippet": (
                        "Revenues (USD) 2024 Q4: 94930000000 filed 2024-11-01 form 10-K; "
                        "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K; "
                        "NetCashProvidedByUsedInOperatingActivities (USD) 2025 Q4: 30000000000 filed 2025-10-31 form 10-K"
                    ),
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_company_facts", "cik": 320193},
                },
                {
                    "title": "SEC 10-K filing for AAPL",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/example/aapl-20250927.htm",
                    "snippet": (
                        "Apple reported quarterly revenue of $102.5 billion, up 6 percent year over year. "
                        "Operating cash flow improved mainly from working capital release."
                    ),
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_recent_filings", "form": "10-K", "cik": 320193},
                },
            ],
        )

        self.assertGreaterEqual(len(pack.atomic_claims), 2)
        self.assertGreaterEqual(len(pack.canonical_facts), 2)
        self.assertIsNotNone(pack.entity_resolution)
        self.assertEqual(pack.entity_resolution.cik, "0000320193")
        self.assertIsNotNone(pack.audit_trace)
        self.assertIn("atomic_claims", pack.to_dict())
        self.assertIn("canonical_facts", pack.to_dict())
        self.assertTrue(any(result.numeric_derivation for result in pack.atomic_claims))
        self.assertTrue(all(result.confidence_components for result in pack.atomic_claims))

    def test_retrieval_budget_is_per_atomic_claim_not_global(self):
        toolkit = FinancialCredibilityToolkit(ToolkitConfig())
        calls = []

        def fake_search(self, claim, ticker, argument_type, max_sources=8, as_of_date=None, prefetched_results=None, selected_sources=None):
            calls.append(claim)
            slug = claim.lower().replace(" ", "-").replace("%", "pct")[:36]
            return [
                SearchResult(
                    title=f"SEC source for {claim}",
                    url=f"https://data.sec.gov/{slug}",
                    snippet=f"{claim}. Official filing excerpt for {ticker}.",
                    published_at="2025-11-01",
                    source="SEC EDGAR",
                    raw={"provider": "sec_recent_filings"},
                )
            ], [f"{claim}: fake result"]

        with patch("financial_credibility.toolkit.SearchClient.search_financial_sources", new=fake_search):
            pack = toolkit.build_evidence_pack(
                claim="Apple revenue grew 6% year over year; Apple debt declined 2%; Apple EPS rose 3%.",
                ticker="AAPL",
                as_of_date="2025-11-01",
                max_sources=1,
            )

        self.assertEqual(len(calls), 3)
        self.assertGreaterEqual(len(pack.evidence), 3)
        self.assertEqual(pack.metadata["retrieval_budget"], 3)
        self.assertEqual(len(pack.metadata["claim_retrievals"]), 3)
        self.assertTrue(all(item["retrieved_count"] == 1 for item in pack.metadata["claim_retrievals"]))
        self.assertEqual(len(pack.metadata["evidence_coverage"]), 3)

    def test_uncovered_conference_call_claim_goes_to_human_review_not_sec_xbrl(self):
        toolkit = FinancialCredibilityToolkit(ToolkitConfig())
        pack = toolkit.build_evidence_pack(
            claim=(
                'During the conference call, Huang said Nvidia\'s new "Vera" central processors '
                "give it access to a new $200 billion market."
            ),
            ticker="NVDA",
            as_of_date="2026-05-20",
        )

        selected = pack.metadata["selected_providers"]
        self.assertNotIn("sec_company_facts", selected)
        self.assertNotIn("market_prices_vendor", selected)
        self.assertEqual(pack.evidence, [])
        self.assertEqual(pack.atomic_claims[0].verdict, VerificationVerdict.INSUFFICIENT)
        self.assertTrue(pack.atomic_claims[0].human_review_required)
        self.assertIn("low_retrieval_sufficiency", pack.atomic_claims[0].review_reasons)
        self.assertIn("search_unavailable", pack.risk_flags)

    def test_single_name_price_move_claim_uses_historical_prices(self):
        points = [
            PricePoint(date(2026, 5, 18), 100.0, 101.0, 99.0, 100.0, 1_000),
            PricePoint(date(2026, 5, 19), 108.0, 109.0, 107.0, 108.0, 1_200),
            PricePoint(date(2026, 5, 20), 101.52, 102.0, 101.0, 101.52, 1_400),
        ]
        toolkit = FinancialCredibilityToolkit(ToolkitConfig())

        with patch("financial_credibility.data_sources.FreeDataSourceClient.stooq_historical_prices", return_value=points):
            pack = toolkit.build_evidence_pack(
                claim="Qualcomm fell 6% after sharp gains on Tuesday.",
                ticker="QCOM",
                as_of_date="2026-05-20",
            )

        self.assertIn("historical_prices", pack.metadata["selected_providers"])
        self.assertTrue(pack.evidence)
        self.assertIn("latest_daily_return_pct -6.0%", pack.evidence[0].text)
        self.assertEqual(pack.numeric_check.verdict, VerificationVerdict.VERIFIED.value)
        self.assertEqual(pack.atomic_claims[0].verdict, VerificationVerdict.SUPPORTED)

    def test_supply_claim_does_not_use_unrelated_eps_evidence(self):
        result = verify_atomic_claims(
            claim=(
                "Nvidia said its supply rose to $119 billion in the fiscal first quarter, "
                "up from $95.2 billion the previous quarter."
            ),
            evidence=[
                Evidence(
                    url="https://data.sec.gov/example",
                    title="SEC Company Facts for NVDA",
                    text="Basic EPS: 2.4 USD/shares for fiscal quarter ended Apr 26, 2026",
                    source_type=SourceType.SEC_FILING,
                    source_tier=SourceTier.T1,
                    domain="data.sec.gov",
                    is_official_primary=True,
                    source_authority=0.95,
                    entity_match_score=0.9,
                )
            ],
            canonical_facts=[],
            entity_resolution=EntityResolution(ticker="NVDA", entity_id="NVDA", confidence=0.9),
        )[0]

        self.assertEqual(result.verdict, VerificationVerdict.INSUFFICIENT)
        self.assertEqual(result.evidence_urls, [])
        self.assertTrue(result.human_review_required)

    def test_atomic_verification_escalates_when_only_non_official_sources_exist(self):
        result = execute_tool(
            "verify_atomic_claim",
            {
                "claim": "Apple revenue grew 6% year over year.",
                "ticker": "AAPL",
                "evidence": [
                    {
                        "title": "Forum post about Apple revenue",
                        "url": "https://example.com/aapl-revenue",
                        "text": "Apple revenue grew 6 percent year over year.",
                        "published_at": "2025-10-31",
                    }
                ],
            },
            ToolkitConfig(),
        )

        atomic = result["atomic_claims"][0]
        self.assertTrue(atomic["human_review_required"])
        self.assertIn("no_official_primary_source", atomic["review_reasons"])

    def test_new_agent_tools_are_registered_and_executable(self):
        names = {tool.name for tool in all_registered_tools()}
        self.assertIn("decompose_claims", names)
        self.assertIn("get_canonical_facts", names)
        self.assertIn("verify_atomic_claim", names)
        self.assertIn("build_audit_trace", names)

        decomposed = execute_tool(
            "decompose_claims",
            {"claim": "Revenue grew; debt declined."},
            ToolkitConfig(),
        )
        routed = execute_tool(
            "route_sources",
            {"claim": "Revenue grew 6% year over year."},
            ToolkitConfig(),
        )
        facts = execute_tool(
            "get_canonical_facts",
            {
                "ticker": "AAPL",
                "search_results": [
                    {
                        "title": "SEC Company Facts for AAPL",
                        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                        "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                        "published_at": "2025-10-31",
                        "source": "SEC EDGAR",
                        "raw": {"provider": "sec_company_facts", "cik": 320193},
                    }
                ],
            },
            ToolkitConfig(),
        )

        self.assertEqual(len(decomposed["claims"]), 2)
        self.assertIn("sec_company_facts", routed["routes"])
        self.assertEqual(len(facts["canonical_facts"]), 1)

    def test_growth_derivation_refuses_duplicate_period_values(self):
        facts = canonicalize_search_results(
            [
                SearchResult(
                    title="SEC Company Facts for AAPL",
                    url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    snippet=(
                        "Revenues (USD) 2026 Q2: 219659000000 filed 2026-05-01 form 10-Q; "
                        "Revenues (USD) 2026 Q2: 95359000000 filed 2026-05-01 form 10-Q"
                    ),
                    published_at="2026-05-01",
                    source="SEC EDGAR",
                    raw={"provider": "sec_company_facts", "cik": 320193},
                )
            ],
            "AAPL",
        )
        numeric = VerificationCheck(
            check_type="numeric_check",
            verdict="not_found",
            confidence=0.25,
            summary="not found",
        )

        self.assertIsNone(derive_numeric_check("Apple revenue grew year over year.", facts, numeric))

    def test_derivation_summarizes_partial_numeric_match_without_period_noise(self):
        numeric = VerificationCheck(
            check_type="numeric_check",
            verdict="partially_verified",
            confidence=0.62,
            summary="Only some material numeric values in the claim were matched directly in the evidence.",
            issues=[
                "matched $81.6 billion with 81,615,000,000",
                "unmatched claim numbers: 85%",
            ],
        )

        derivation = derive_numeric_check(
            "In fiscal 2027 Q1, NVIDIA reported total revenue of $81.6 billion, up 85% year over year.",
            [],
            numeric,
        )

        self.assertIsNotNone(derivation)
        self.assertEqual(derivation.expression, "numeric_match_summary")
        self.assertEqual(derivation.inputs["unmatched_values"], "85%")

    def test_unrelated_sec_facts_are_not_used_for_conference_call_claim(self):
        claim = (
            'During the conference call, Huang said Nvidia\'s new "Vera" central processors '
            "give it access to a new $200 billion market."
        )
        source = assess_source("https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json")
        evidence = [
            Evidence(
                url="https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json",
                title="SEC Company Facts for NVDA",
                text=(
                    "EarningsPerShareBasic (USD/shares) for fiscal quarter ending 2026-04-26: "
                    "2.40 (form 10-Q); EarningsPerShareBasic (USD/shares) for fiscal year ending "
                    "2026-01-25: 4.93 (form 10-K)"
                ),
                source_type=source.source_type,
                source_tier=source.source_tier,
                domain=source.domain,
                published_at="2026-05-20",
                license_tag=source.license_tag,
                is_official_primary=True,
            )
        ]
        facts = canonicalize_evidence(evidence, "NVDA")

        result = verify_atomic_claims(
            claim=claim,
            evidence=evidence,
            canonical_facts=facts,
            entity_resolution=EntityResolution(ticker="NVDA", entity_id="NVDA", confidence=0.95),
        )[0]

        self.assertEqual(result.verdict, VerificationVerdict.INSUFFICIENT)
        self.assertEqual(result.evidence_urls, [])
        self.assertEqual(result.canonical_fact_ids, [])
        self.assertTrue(result.human_review_required)
        self.assertIn("no_evidence", result.issues)

    def test_margin_derivation_recomputes_from_base_facts(self):
        facts = canonicalize_search_results(
            [
                SearchResult(
                    title="SEC Company Facts for AAPL",
                    url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    snippet=(
                        "GrossProfit (USD) 2025 Q4: 50000000000 filed 2025-10-31 form 10-K; "
                        "Revenues (USD) 2025 Q4: 100000000000 filed 2025-10-31 form 10-K"
                    ),
                    published_at="2025-10-31",
                    source="SEC EDGAR",
                    raw={"provider": "sec_company_facts", "cik": 320193},
                )
            ],
            "AAPL",
        )
        numeric = VerificationCheck("numeric_check", "not_found", 0.25, "not found")

        derivation = derive_numeric_check("Apple gross margin was above 45%.", facts, numeric)

        self.assertIsNotNone(derivation)
        self.assertEqual(derivation.expression, "GrossProfit / Revenue")
        self.assertEqual(derivation.result, 0.5)
        self.assertTrue(derivation.passed)

    def test_price_claim_without_return_derivation_is_insufficient(self):
        evidence = [
            Evidence(
                url="https://stooq.com/q/l/?s=snow.us",
                title="Stooq latest quote for SNOW",
                text="SNOW latest quote: date 2026-05-28 close 239.19 open 237 high 242.11 low 229.49",
                source_type=SourceType.DATA_VENDOR,
                source_tier=SourceTier.T4,
                domain="stooq.com",
                relevance_score=0.4,
                numeric_consistency_score=0.25,
                support_score=0.0,
            )
        ]

        result = verify_atomic_claims(
            claim="Snowflake rose 34.1% after profit.",
            evidence=evidence,
            canonical_facts=[],
            entity_resolution=EntityResolution(ticker="SNOW", entity_id="SNOW", confidence=0.86),
        )[0]

        self.assertEqual(result.verdict, VerificationVerdict.INSUFFICIENT)

    def test_price_claim_ignores_sec_financial_statement_evidence(self):
        evidence = [
            Evidence(
                url="https://www.sec.gov/Archives/example",
                title="Apple press release filed with SEC",
                text="Apple posted quarterly revenue of $111.2 billion and diluted EPS of $2.01.",
                source_type=SourceType.SEC_FILING,
                source_tier=SourceTier.T1,
                domain="sec.gov",
                is_official_primary=True,
                relevance_score=0.8,
                numeric_consistency_score=0.8,
            )
        ]

        result = verify_atomic_claims(
            claim="Apple's share price was down about 0.5% in after-hours trading.",
            evidence=evidence,
            canonical_facts=[],
            entity_resolution=EntityResolution(ticker="AAPL", entity_id="AAPL", confidence=0.86),
        )[0]

        self.assertEqual(result.verdict, VerificationVerdict.INSUFFICIENT)
        self.assertEqual(result.evidence_urls, [])

    def test_free_cash_flow_derivation_recomputes_amount(self):
        facts = canonicalize_search_results(
            [
                SearchResult(
                    title="SEC Company Facts for AAPL",
                    url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    snippet=(
                        "NetCashProvidedByUsedInOperatingActivities (USD) 2025 FY: 10000000000 filed 2025-10-31 form 10-K; "
                        "PaymentsToAcquirePropertyPlantAndEquipment (USD) 2025 FY: 3000000000 filed 2025-10-31 form 10-K"
                    ),
                    published_at="2025-10-31",
                    source="SEC EDGAR",
                    raw={"provider": "sec_company_facts", "cik": 320193},
                )
            ],
            "AAPL",
        )
        numeric = VerificationCheck("numeric_check", "not_found", 0.25, "not found")

        derivation = derive_numeric_check("Apple free cash flow was $7 billion.", facts, numeric)

        self.assertIsNotNone(derivation)
        self.assertEqual(derivation.result, 7000000000)
        self.assertTrue(derivation.passed)

    def test_claim_verdict_uses_recomputed_derivation(self):
        facts = canonicalize_search_results(
            [
                SearchResult(
                    title="SEC Company Facts for AAPL",
                    url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    snippet=(
                        "GrossProfit (USD) 2025 Q4: 50000000000 filed 2025-10-31 form 10-K; "
                        "Revenues (USD) 2025 Q4: 100000000000 filed 2025-10-31 form 10-K"
                    ),
                    published_at="2025-10-31",
                    source="SEC EDGAR",
                    raw={"provider": "sec_company_facts", "cik": 320193},
                )
            ],
            "AAPL",
        )
        result = execute_tool(
            "verify_atomic_claim",
            {
                "claim": "Apple gross margin was above 45%.",
                "ticker": "AAPL",
                "canonical_facts": [to_plain(fact) for fact in facts],
                "evidence": [
                    {
                        "title": "SEC Company Facts for AAPL",
                        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                        "text": "GrossProfit and Revenues are official SEC XBRL company facts.",
                        "published_at": "2025-10-31",
                    }
                ],
            },
            ToolkitConfig(),
        )

        atomic = result["atomic_claims"][0]
        self.assertEqual(atomic["verdict"], "supported")
        self.assertEqual(atomic["numeric_derivation"]["expression"], "GrossProfit / Revenue")


if __name__ == "__main__":
    unittest.main()
