import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.data_sources import FreeDataSourceClient


class DataSourceClientTests(unittest.TestCase):
    def test_sec_concepts_for_revenue_claim(self):
        client = FreeDataSourceClient(ToolkitConfig())
        concepts = client._concepts_for_claim("Apple revenue grew 6% year over year.")
        self.assertIn("Revenues", concepts)

    def test_fred_series_for_macro_claim(self):
        client = FreeDataSourceClient(ToolkitConfig(fred_api_key="demo"))
        self.assertEqual(client._fred_series_for_claim("Inflation is falling."), "CPIAUCSL")


if __name__ == "__main__":
    unittest.main()
