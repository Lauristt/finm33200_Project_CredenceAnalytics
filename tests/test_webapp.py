import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.webapp import HTML, _handler, _statement_from_payload


class WebappTests(unittest.TestCase):
    def test_chat_ui_has_single_visible_statement_input(self):
        self.assertIn('id="statement"', HTML)
        self.assertNotIn('id="tickers"', HTML)
        self.assertNotIn('id="max_sources"', HTML)
        self.assertNotIn('id="mode"', HTML)
        self.assertNotIn(">Memo<", HTML)
        self.assertIn("Credence Analytics Agent", HTML)
        self.assertNotIn("Official Evidence Verifier", HTML)
        self.assertIn("/api/report/stream", HTML)
        self.assertIn('id="stop"', HTML)
        self.assertIn("AbortController", HTML)
        self.assertIn("currentRunController.abort()", HTML)
        self.assertIn("Run stopped", HTML)
        self.assertIn('replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>")', HTML)
        self.assertIn(">Trace<", HTML)
        self.assertNotIn("Live Agent Trace", HTML)
        self.assertIn("details class=\"trace-panel", HTML)
        self.assertIn("Rendered Report", HTML)
        self.assertIn("renderMarkdown(markdown)", HTML)
        self.assertIn("Raw Markdown", HTML)
        self.assertIn("formatError", HTML)
        self.assertIn("Detected Asset Classes", HTML)
        self.assertIn('details class="asset-group"', HTML)
        self.assertIn("asset-group-items", HTML)
        self.assertIn("assetClassLabel", HTML)
        self.assertIn("Claim Checks", HTML)
        self.assertIn("Fact Checks", HTML)
        self.assertIn("Not Fact-Checked", HTML)
        self.assertIn("Data Source Checked", HTML)
        self.assertIn("What The Source Says", HTML)
        self.assertIn("humanPriceHistoryLines", HTML)
        self.assertIn("parsePriceHistoryEvidence", HTML)
        self.assertIn("Tool called: historical_prices adapter", HTML)
        self.assertIn("Claim comparison:", HTML)
        self.assertIn("Evidence summary", HTML)
        self.assertNotIn("Price evidence", HTML)
        self.assertIn("Does It Match The Claim?", HTML)
        self.assertIn('text === "ticker_only_entity_resolution"', HTML)
        self.assertIn('text === "llm_judge_unavailable"', HTML)
        self.assertIn("entity resolution is based mainly on the ticker symbol", HTML)
        self.assertIn("humanFactName", HTML)
        self.assertIn("RevenueFromContractWithCustomerExcludingAssessedTax: \"Revenue\"", HTML)
        self.assertIn("formatFactValue", HTML)
        self.assertIn("isDisplayableFact", HTML)
        self.assertIn("/^SEC Company Facts", HTML)
        self.assertIn("Human Review", HTML)
        self.assertNotIn("Verification Confidence", HTML)
        self.assertNotIn("Verification confidence", HTML)
        self.assertIn("needs-review", HTML)
        self.assertIn("liveTraceOpenDetails", HTML)
        self.assertIn("rememberLiveTraceDetailState", HTML)
        self.assertIn("restoreLiveTraceDetailState", HTML)
        self.assertIn("data-detail-key", HTML)
        self.assertIn("Selected Sources", HTML)
        self.assertNotIn("Why These Sources Were Selected", HTML)
        self.assertNotIn("Source routing", HTML)
        self.assertNotIn("Entity Extraction", HTML)
        self.assertNotIn("llm_openai", HTML)
        self.assertNotIn("known_alias", HTML)
        self.assertNotIn("<th>Review</th>", HTML)
        self.assertNotIn("<th>Derivation</th>", HTML)
        self.assertNotIn('class="trace-panel live-trace" open', HTML)
        self.assertNotIn('class="trace-panel" open', HTML)

    def test_statement_payload_takes_precedence_over_legacy_memo(self):
        self.assertEqual(
            _statement_from_payload({"statement": "Apple revenue grew.", "memo": "legacy"}),
            "Apple revenue grew.",
        )
        self.assertEqual(_statement_from_payload({"memo": "legacy"}), "legacy")

    def test_report_api_accepts_multi_tool_mode(self):
        handler_cls = _handler(ToolkitConfig())
        handler = object.__new__(handler_cls)
        payload = handler._build_report(
            {
                "statement": "Apple revenue grew 6% year over year.",
                "tickers": ["AAPL"],
                "mode": "multi_tool",
                "prefetched_results": [
                    {
                        "title": "SEC Company Facts for AAPL",
                        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                        "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                        "published_at": "2025-10-31",
                        "source": "SEC EDGAR",
                        "raw": {"provider": "sec_company_facts", "cik": 320193},
                    }
                ],
            }
        )

        self.assertIn("agent_trace", payload)
        self.assertEqual(payload["input"]["mode"], "multi_tool")


if __name__ == "__main__":
    unittest.main()
