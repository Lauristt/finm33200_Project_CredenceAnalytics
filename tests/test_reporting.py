import unittest

from financial_credibility.reporting import build_verification_report, infer_tickers
from financial_credibility.config import ToolkitConfig


class ReportingTests(unittest.TestCase):
    def test_infer_tickers_from_memo(self):
        self.assertEqual(infer_tickers("Apple ($AAPL) and Microsoft (MSFT) revenue grew."), ["AAPL", "MSFT"])

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
        self.assertIn("Not Fact-Checked", payload["report_markdown"])
        self.assertIn("Agent Trace", payload["report_markdown"])
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
        self.assertIn("Detected Asset Classes", payload["report_markdown"])
        self.assertIn("Single-name equities", payload["report_markdown"])
        self.assertNotIn("Method:", payload["report_markdown"])

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


if __name__ == "__main__":
    unittest.main()
