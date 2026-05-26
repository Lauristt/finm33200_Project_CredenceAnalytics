import unittest
from datetime import date

from financial_credibility.config import ToolkitConfig
from financial_credibility.data_sources import FreeDataSourceClient
from financial_credibility.price_history import (
    PricePoint,
    needs_historical_price_data,
    parse_lookback_months,
    summarize_price_history,
)


class DataSourceClientTests(unittest.TestCase):
    def test_sec_concepts_for_revenue_claim(self):
        client = FreeDataSourceClient(ToolkitConfig())
        concepts = client._concepts_for_claim("Apple revenue grew 6% year over year.")
        self.assertIn("Revenues", concepts)

    def test_sec_concept_matcher_handles_custom_revenue_tags(self):
        client = FreeDataSourceClient(ToolkitConfig())
        facts = {
            "us-gaap": {"Revenues": {"units": {"USD": []}}},
            "nvda": {"DataCenterRevenue": {"units": {"USD": []}}},
        }

        matches = client._matching_sec_concepts(
            facts,
            ["Revenues"],
            "NVIDIA data center revenue represented more than 80% of total revenue.",
        )

        self.assertEqual([concept for concept, _ in matches], ["Revenues", "DataCenterRevenue"])

    def test_fred_series_for_macro_claim(self):
        client = FreeDataSourceClient(ToolkitConfig(fred_api_key="demo"))
        self.assertEqual(client._fred_series_for_claim("Inflation is falling."), "CPIAUCSL")

    def test_price_pattern_claim_needs_historical_prices(self):
        claim = "Nvidia's stock price seems like oscillating these months (10 months)."
        self.assertTrue(needs_historical_price_data(claim))
        self.assertEqual(parse_lookback_months(claim), 10)

    def test_price_history_summary_detects_oscillation(self):
        points = [
            PricePoint(date(2025, 1, 31), 100, 101, 99, 100),
            PricePoint(date(2025, 2, 28), 130, 131, 129, 130),
            PricePoint(date(2025, 3, 31), 95, 96, 94, 95),
            PricePoint(date(2025, 4, 30), 125, 126, 124, 125),
            PricePoint(date(2025, 5, 31), 90, 91, 89, 90),
            PricePoint(date(2025, 6, 30), 120, 121, 119, 120),
        ]
        summary = summarize_price_history(points)

        self.assertIsNotNone(summary)
        self.assertGreaterEqual(summary.monthly_direction_changes, 3)
        self.assertIn(summary.oscillation_signal, {"moderate", "strong"})


if __name__ == "__main__":
    unittest.main()
