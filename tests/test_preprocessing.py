import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.preprocessing import preprocess_statement
from financial_credibility.reporting import build_verification_report
from financial_credibility.tool_runtime import execute_tool


class PreprocessingTests(unittest.TestCase):
    def test_removes_copied_webpage_ads_without_losing_market_claims(self):
        raw = """
        Subscribe
        Advertisement
        How major US stock indexes fared Tuesday 5/26/2026

        The S&P 500 added 0.6% Tuesday after trading resumed following Monday's holiday.

        On Tuesday:
        The S&P 500 rose 45.65 points, or 0.6%, to 7,519.12.

        Paid for by Visit Sarasota County
        Sail, Spa, Savor: Sarasota in Style
        Here on Florida's Gulf Coast, the Sarasota area has mastered luxury that feels understated rather than extravagant.
        Visit Sarasota County logo
        """

        cleaned = preprocess_statement(raw)

        self.assertTrue(cleaned.changed)
        self.assertIn("The S&P 500 added 0.6% Tuesday", cleaned.clean_text)
        self.assertIn("On Tuesday:", cleaned.clean_text)
        self.assertNotIn("Subscribe", cleaned.clean_text)
        self.assertNotIn("Paid for by", cleaned.clean_text)
        self.assertNotIn("Sarasota", cleaned.clean_text)
        self.assertGreaterEqual(len(cleaned.removed_lines), 4)

    def test_preprocess_tool_returns_cleaned_statement(self):
        result = execute_tool(
            "preprocess_statement",
            {"statement": "Advertisement\nApple revenue grew 6% year over year.\nSubscribe"},
            ToolkitConfig(),
        )

        self.assertTrue(result["changed"])
        self.assertEqual(result["cleaned_statement"], "Apple revenue grew 6% year over year.")
        self.assertEqual(result["removed_line_count"], 2)

    def test_report_flow_uses_cleaned_memo_metadata(self):
        payload = build_verification_report(
            memo=(
                "Advertisement\n"
                "Apple revenue grew 6% year over year.\n"
                "Paid for by Example Sponsor\n"
                "Unrelated travel promotion logo\n"
            ),
            tickers=["AAPL"],
            config=ToolkitConfig(),
            mode="strict",
            prefetched_results=[
                {
                    "title": "Apple reports results",
                    "url": "https://www.apple.com/newsroom/example",
                    "snippet": "Apple revenue grew 6% year over year.",
                    "published_at": "2025-10-30",
                }
            ],
        )

        self.assertIn("Apple revenue grew 6% year over year.", payload["input"]["memo"])
        self.assertNotIn("Advertisement", payload["input"]["memo"])
        self.assertNotIn("Paid for by", payload["input"]["memo"])
        self.assertTrue(payload["input"]["preprocessing"]["changed"])
        self.assertIn("Advertisement", payload["input"]["original_memo"])


if __name__ == "__main__":
    unittest.main()
