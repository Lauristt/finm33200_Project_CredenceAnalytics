import unittest

from financial_credibility.webapp import HTML, _statement_from_payload


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
        self.assertIn(">Trace<", HTML)
        self.assertNotIn("Live Agent Trace", HTML)
        self.assertIn("details class=\"trace-panel", HTML)
        self.assertIn("Rendered Report", HTML)
        self.assertIn("renderMarkdown(markdown)", HTML)
        self.assertIn("Raw Markdown", HTML)
        self.assertIn("Detected Asset Classes", HTML)
        self.assertIn('details class="asset-group"', HTML)
        self.assertIn("asset-group-items", HTML)
        self.assertIn("assetClassLabel", HTML)
        self.assertIn("Claim Checks", HTML)
        self.assertIn("Fact Checks", HTML)
        self.assertIn("Not Fact-Checked", HTML)
        self.assertIn("Data Source Checked", HTML)
        self.assertIn("What The Source Says", HTML)
        self.assertIn("Does It Match The Claim?", HTML)
        self.assertIn("Human Review", HTML)
        self.assertIn("needs-review", HTML)
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


if __name__ == "__main__":
    unittest.main()
