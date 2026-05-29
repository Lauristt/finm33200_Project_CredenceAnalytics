import unittest

from financial_credibility.reporting import build_verification_report, infer_tickers, render_markdown_report
from financial_credibility.config import ToolkitConfig


class ReportingTests(unittest.TestCase):
    def test_infer_tickers_from_memo(self):
        self.assertEqual(infer_tickers("Apple ($AAPL) and Microsoft (MSFT) revenue grew."), ["AAPL", "MSFT"])

    def test_infer_tickers_ignores_pm_time_suffix(self):
        self.assertEqual(infer_tickers("Published 05/20/2026, 04:26 PM"), [])

    def test_infer_tickers_ignores_news_stopwords(self):
        self.assertEqual(infer_tickers("How major US stock indexes fared Tuesday"), [])

    def test_build_report_payload_contains_markdown_and_runs(self):
        progress = []
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year. Apple stock remains attractive.",
            tickers=["AAPL"],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "SEC Company Facts for AAPL",
                    "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_company_facts", "cik": 320193},
                },
                {
                    "title": "Apple reports fourth quarter results",
                    "url": "https://www.apple.com/newsroom/example",
                    "snippet": "Apple reported quarterly revenue up 6 percent year over year.",
                    "published_at": "2025-10-30",
                },
            ],
            progress_callback=progress.append,
        )

        self.assertEqual(payload["summary"]["entity_count"], 1)
        self.assertEqual(payload["summary"]["atomic_claim_count"], 1)
        self.assertEqual(payload["summary"]["skipped_claim_count"], 1)
        self.assertIn("Credence Verification Report", payload["report_markdown"])
        self.assertIn("Bottom Line", payload["report_markdown"])
        self.assertIn("Not fact-checked", payload["report_markdown"])
        self.assertNotIn("Agent Trace", payload["report_markdown"])
        self.assertNotIn("Audit trace:", payload["report_markdown"])
        self.assertNotIn("Entity:", payload["report_markdown"])
        self.assertEqual(payload["runs"][0]["ticker"], "AAPL")
        self.assertIn("extract_entities", [event["step"] for event in progress])
        self.assertIn("retrieve", [event["step"] for event in progress])
        self.assertEqual(progress[-1]["step"], "compose_report")

    def test_build_report_extracts_ticker_when_not_supplied(self):
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year.",
            tickers=[],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "SEC Company Facts for AAPL",
                    "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_company_facts", "cik": 320193},
                }
            ],
        )

        self.assertEqual(payload["input"]["tickers"], ["AAPL"])
        self.assertEqual(payload["input"]["entity_extraction"]["method"], "heuristic")
        self.assertNotIn("Method:", payload["report_markdown"])
        self.assertNotIn("Detected Asset Classes", payload["report_markdown"])
        self.assertNotIn("Verification Coverage", payload["report_markdown"])
        self.assertEqual(payload["coverage_summary"]["fully_verified_entities"][0]["ticker"], "AAPL")
        self.assertNotIn("Evidence Provenance", payload["report_markdown"])
        self.assertNotIn("Claim Explanations", payload["report_markdown"])
        self.assertNotIn("Source Selection Explanation", payload["report_markdown"])
        self.assertTrue(payload["runs"][0]["source_selection_debug"])
        self.assertTrue(payload["runs"][0]["audit_export"]["download_ready"])

    def test_build_report_uses_source_seed_without_replacing_live_retrieval_contract(self):
        payload = build_verification_report(
            memo=(
                "Microsoft reported fiscal third-quarter revenue of $82.9 billion for the quarter ended "
                "March 31, 2026, up 18% year over year."
            ),
            tickers=["MSFT"],
            config=ToolkitConfig(enable_structured_sources=False),
            as_of_date="2026-04-29",
            source_results=[
                {
                    "title": "Microsoft Cloud and AI Strength Fuels Third Quarter Results",
                    "url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast",
                    "snippet": (
                        "Revenue was $82.9 billion and increased 18% for the quarter ended March 31, 2026."
                    ),
                    "published_at": "2026-04-29",
                    "source": "Microsoft Investor Relations",
                }
            ],
        )

        markdown = payload["report_markdown"]
        self.assertIn("Consistent", markdown)
        self.assertIn("microsoft.com", markdown)
        self.assertIn("The evidence directly matches $82.9 billion and 18%", markdown)

    def test_build_report_with_only_non_equity_entities_does_not_force_ticker_run(self):
        payload = build_verification_report(
            memo="CPI surprised higher while WTI and EUR/USD moved sharply.",
            tickers=[],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[],
        )

        self.assertEqual(payload["input"]["tickers"], [])
        self.assertEqual(payload["runs"], [])
        self.assertEqual(payload["summary"]["asset_class_count"], 3)
        self.assertIn("Macro indicators", payload["report_markdown"])
        self.assertIn("Commodities", payload["report_markdown"])
        self.assertIn("FX", payload["report_markdown"])
        self.assertNotIn("Verification Coverage", payload["report_markdown"])
        self.assertEqual(
            sorted(payload["coverage_summary"]["unsupported_asset_classes"]),
            ["commodity", "fx", "macro_indicator"],
        )

    def test_build_report_runs_price_verification_targets_for_equity_indexes(self):
        payload = build_verification_report(
            memo=(
                "How major US stock indexes fared Tuesday 5/26/2026. "
                "The S&P 500 added 0.6% Tuesday. "
                "The Nasdaq composite climbed 1.2%. "
                "The Dow Jones Industrial Average slipped 0.2%. "
                "The Russell 2000 index rose 1.8%."
            ),
            tickers=[],
            config=ToolkitConfig(),
            as_of_date="2026-05-27",
            prefetched_results=[],
        )

        self.assertEqual(payload["input"]["tickers"], ["SPX", "NDQ", "DJIA", "RUT"])
        self.assertEqual([run["ticker"] for run in payload["runs"]], ["SPX", "NDQ", "DJIA", "RUT"])
        self.assertNotIn("US", payload["input"]["tickers"])
        self.assertNotIn("THE", payload["input"]["tickers"])
        statuses = {
            item["symbol"] or item["ticker"]: item["verification_status"]
            for item in payload["coverage_summary"]["entities"]
        }
        self.assertEqual(statuses["SPX"], "fully_verified")
        self.assertEqual(statuses["NDQ"], "fully_verified")
        self.assertEqual(statuses["DJIA"], "fully_verified")
        self.assertEqual(statuses["RUT"], "fully_verified")

    def test_build_report_infers_event_date_as_retrieval_anchor(self):
        payload = build_verification_report(
            memo=(
                "How major US stock indexes fared Tuesday 5/26/2026. "
                "Published 05/27/2026, 04:26 PM. "
                "The S&P 500 added 0.6% Tuesday."
            ),
            tickers=[],
            config=ToolkitConfig(),
            prefetched_results=[],
        )

        self.assertEqual(payload["input"]["as_of_date"], "2026-05-26")
        self.assertEqual(payload["input"]["time_context"]["source"], "explicit_event_date")
        self.assertTrue(payload["runs"])
        self.assertEqual(payload["runs"][0]["as_of_date"], "2026-05-26")

    def test_auto_extracted_multi_entity_report_scopes_claims(self):
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year while Microsoft debt declined.",
            tickers=[],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "SEC Company Facts for AAPL",
                    "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_company_facts", "cik": 320193},
                }
            ],
        )

        self.assertEqual(payload["input"]["tickers"], ["AAPL", "MSFT"])
        self.assertEqual(payload["runs"][0]["claim"], "Apple revenue grew 6% year over year")
        self.assertEqual(payload["runs"][1]["claim"], "Microsoft debt declined")

    def test_mixed_equity_and_macro_coverage_summary(self):
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year while CPI rose and WTI rallied.",
            tickers=[],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "SEC Company Facts for AAPL",
                    "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_company_facts", "cik": 320193},
                }
            ],
        )

        statuses = {
            item["symbol"] or item["ticker"]: item["verification_status"]
            for item in payload["coverage_summary"]["entities"]
        }
        self.assertEqual(statuses["AAPL"], "fully_verified")
        self.assertEqual(statuses["CPI"], "detected_only")
        self.assertEqual(statuses["WTI"], "detected_only")
        self.assertIn("Detected but not fully checked", payload["report_markdown"])

    def test_report_renders_human_review_explanations(self):
        payload = build_verification_report(
            memo="Apple revenue accelerated due to stronger demand.",
            tickers=["AAPL"],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "Market blog says revenue accelerated",
                    "url": "https://example.com/market-blog/aapl",
                    "snippet": "Apple revenue accelerated due to demand, according to a blog.",
                    "published_at": "2025-10-31",
                    "source": "Market Blog",
                }
            ],
        )

        self.assertNotIn("Human Review Explanations", payload["report_markdown"])
        self.assertNotIn("Recommended action", payload["report_markdown"])

    def test_report_explains_insufficient_result_with_linked_evidence(self):
        markdown = render_markdown_report(
            {
                "summary": {"atomic_claim_count": 1, "entity_count": 1, "human_review_count": 1},
                "runs": [
                    {
                        "ticker": "AAPL",
                        "evidence": [
                            {
                                "title": "SEC Company Facts for AAPL",
                                "url": "https://data.sec.gov/example",
                                "domain": "data.sec.gov",
                                "source_tier": "T1",
                                "is_official_primary": True,
                            }
                        ],
                        "atomic_claims": [
                            {
                                "atomic_claim": {"claim_id": "claim_1", "text": "Apple reported revenue of $111.2 billion."},
                                "verdict": "insufficient",
                                "evidence_urls": ["https://data.sec.gov/example"],
                                "review_reasons": ["ambiguous_unit_currency_or_period"],
                            }
                        ],
                        "claim_explanations": [],
                    }
                ],
            }
        )

        self.assertIn("Evidence was retrieved, but the exact value, unit, or reporting period was not matched clearly.", markdown)
        self.assertIn("Needs human review", markdown)

    def test_sec_evidence_provenance_marks_official_primary(self):
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year.",
            tickers=["AAPL"],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "SEC Company Facts for AAPL",
                    "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                    "published_at": "2025-10-31",
                    "source": "SEC EDGAR",
                    "raw": {"provider": "sec_company_facts", "cik": 320193},
                }
            ],
        )

        provenance = payload["runs"][0]["evidence_provenance"][0]
        self.assertTrue(provenance["is_official_primary"])
        self.assertEqual(provenance["source_tier"], "T1")
        self.assertEqual(provenance["license_tag"], "public_official")
        self.assertIn("claim_1", provenance["used_by_claims"])

    def test_source_selection_debug_handles_empty_selection(self):
        payload = {
            "summary": {},
            "input": {"entity_extraction": {}},
            "runs": [
                {
                    "ticker": "AAPL",
                    "overall_conclusion": {},
                    "metadata": {"source_selection": []},
                    "audit_trace": {},
                    "atomic_claims": [],
                    "evidence": [],
                }
            ],
            "errors": [],
        }

        markdown = render_markdown_report(payload)

        self.assertIn("Credence Verification Report", markdown)


if __name__ == "__main__":
    unittest.main()
