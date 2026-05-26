import unittest

from financial_credibility import FinancialCredibilityToolkit
from financial_credibility.claims import decompose_claims
from financial_credibility.config import ToolkitConfig
from financial_credibility.derivations import derive_numeric_check
from financial_credibility.facts import canonicalize_search_results
from financial_credibility.models import SearchResult, VerificationCheck, to_plain
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
