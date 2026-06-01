"""Optional live API smoke tests for cross-asset official-source adapters.

These tests are intentionally skipped by default. They are for local coverage
checks after keys are configured, not for deterministic CI.

Run with:
    CREDIBILITY_RUN_LIVE_API_TESTS=true PYTHONPATH=src python3 -m pytest -q tests/test_live_asset_source_smoke.py
"""

from __future__ import annotations

import os
import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.data_sources import FreeDataSourceClient


RUN_LIVE = os.getenv("CREDIBILITY_RUN_LIVE_API_TESTS", "").lower() in {"1", "true", "yes"}


@unittest.skipUnless(RUN_LIVE, "set CREDIBILITY_RUN_LIVE_API_TESTS=true to run live API smoke tests")
class LiveAssetSourceSmokeTests(unittest.TestCase):
    def setUp(self):
        self.config = ToolkitConfig.from_env()
        self.client = FreeDataSourceClient(self.config)

    def test_fred_bls_bea_eia_primary_adapters_return_rows(self):
        checks = [
            ("fred", lambda: self.client.fred("SOFR rose.", as_of_date="2026-05-27"), self.config.fred_api_key),
            ("bls_api", lambda: self.client.bls_api("BLS CPI increased.", as_of_date="2026-05-27"), True),
            ("bea_api", lambda: self.client.bea_api("BEA GDP grew.", as_of_date="2026-05-27"), self.config.bea_api_key),
            ("eia_api", lambda: self.client.eia_api("EIA WTI crude oil price rose.", as_of_date="2026-05-27"), self.config.eia_api_key),
        ]
        for name, call, enabled in checks:
            with self.subTest(name=name):
                if not enabled:
                    self.skipTest(f"{name} credential not configured")
                results = call()
                self.assertTrue(results, f"{name} returned no rows")
                self.assertEqual(results[0].raw["provider"], name)

    def test_no_key_global_public_adapters_return_rows_when_series_mapping_exists(self):
        checks = [
            ("cftc_cot", lambda: self.client.cftc_cot("CFTC COT gold open interest rose.")),
            ("ecb_data_portal", lambda: self.client.ecb_data_portal("ECB deposit facility rate changed.")),
            ("bis_data_portal", lambda: self.client.bis_data_portal("BIS cross-border banking claims grew.")),
            ("imf_data_api", lambda: self.client.imf_data_api("IMF WEO US GDP growth from 2024 to 2025")),
            ("world_bank_indicators", lambda: self.client.world_bank_indicators("World Bank China GDP from 2020 to 2023")),
            ("bank_of_england", lambda: self.client.bank_of_england("Bank of England Bank Rate changed.")),
        ]
        for name, call in checks:
            with self.subTest(name=name):
                results = call()
                self.assertTrue(results, f"{name} returned no rows")
                self.assertEqual(results[0].raw["provider"], name)

    def test_finra_query_api_returns_fixed_income_rows_when_credentials_are_configured(self):
        if not self.config.finra_client_id or not self.config.finra_client_secret:
            self.skipTest("FINRA credentials not configured")

        results = self.client.finra_query_api("FINRA TRACE corporate bond trading volumes increased.", limit=5)

        self.assertTrue(results, "finra_query_api returned no rows")
        if results[0].raw.get("status_code") in {401, 403}:
            self.skipTest("FINRA credential works, but this fixed-income dataset is not entitled")
        self.assertEqual(results[0].raw["provider"], "finra_query_api")


if __name__ == "__main__":
    unittest.main()
