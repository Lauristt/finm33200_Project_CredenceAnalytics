import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.news_benchmark import CROSS_ASSET_NEWS_CASES, evaluate_news_benchmark


class CrossAssetNewsBenchmarkTests(unittest.TestCase):
    def test_recent_news_benchmark_covers_all_supported_asset_classes(self):
        result = evaluate_news_benchmark(ToolkitConfig(enable_ticker_universe_filter=False))

        self.assertEqual(result["failed_count"], 0)
        self.assertGreaterEqual(result["case_count"], 30)
        self.assertEqual(
            set(result["covered_asset_classes"]),
            {
                "single_name_equity",
                "equity_index",
                "equity_index_future",
                "fund_etf",
                "macro_indicator",
                "rates",
                "credit",
                "fixed_income",
                "commodity",
                "commodity_future",
                "fx",
                "derivatives",
            },
        )

    def test_each_benchmark_case_has_source_url_and_expected_mapping(self):
        for case in CROSS_ASSET_NEWS_CASES:
            with self.subTest(case_id=case.case_id):
                self.assertTrue(case.source_urls)
                self.assertTrue(case.expected_sources)
                self.assertTrue(case.expected_series)


if __name__ == "__main__":
    unittest.main()
