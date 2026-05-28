import unittest
from unittest.mock import patch

from financial_credibility.config import ToolkitConfig
from financial_credibility.data_sources import FreeDataSourceClient
from financial_credibility.models import ArgumentType, SearchResult
from financial_credibility.routing import route_sources
from financial_credibility.source_selection import (
    candidate_sources_for_claim,
    candidate_sources_for_claim_with_options,
    load_source_detail,
    select_sources_for_claims,
    source_catalog,
    selected_source_details,
    selected_provider_names_from_plan,
    validate_source_selection,
)
from financial_credibility.tool_runtime import execute_tool


class SourceSelectionTests(unittest.TestCase):
    def test_candidate_sources_include_sec_for_revenue_claim(self):
        candidates = candidate_sources_for_claim("Apple revenue grew 6% year over year.")
        ids = [item["source_id"] for item in candidates]

        self.assertIn("sec_company_facts", ids)
        self.assertIn("sec_recent_filings", ids)
        self.assertIn("brief_description", candidates[0])
        self.assertNotIn("detail_markdown", candidates[0])
        self.assertTrue(all(item["is_runtime_selectable"] for item in candidates))

    def test_no_key_official_sources_are_runtime_selectable(self):
        examples = [
            ("CFTC COT gold open interest increased.", "cftc_cot"),
            ("ECB euro area HICP inflation declined.", "ecb_data_portal"),
            ("BIS cross-border banking claims grew.", "bis_data_portal"),
            ("IMF WEO US GDP growth increased.", "imf_data_api"),
            ("World Bank US GDP increased.", "world_bank_indicators"),
            ("Bank of England Bank Rate was cut.", "bank_of_england"),
            ("Map AAPL to FIGI using OpenFIGI.", "openfigi"),
        ]

        for claim, source_id in examples:
            with self.subTest(source_id=source_id):
                candidates = candidate_sources_for_claim(claim)
                by_id = {item["source_id"]: item for item in candidates}
                self.assertIn(source_id, by_id)
                self.assertTrue(by_id[source_id]["is_runtime_selectable"])
                self.assertEqual(by_id[source_id]["adapter_status"], "implemented")

    def test_candidate_sources_can_include_planned_official_library(self):
        candidates = candidate_sources_for_claim_with_options(
            "Federal Reserve Z.1 financial accounts should be checked.",
            include_planned=True,
        )
        ids = [item["source_id"] for item in candidates]

        self.assertIn("federal_reserve_ddp", ids)
        self.assertTrue(any(not item["is_runtime_selectable"] for item in candidates))

    def test_candidate_sources_include_runtime_world_bank_for_country_indicator(self):
        candidates = candidate_sources_for_claim("China GDP data from 2015 to 2023.")
        ids = [item["source_id"] for item in candidates]

        self.assertIn("world_bank_indicators", ids)
        world_bank = next(item for item in candidates if item["source_id"] == "world_bank_indicators")
        self.assertEqual(world_bank["adapter_status"], "implemented")
        self.assertTrue(world_bank["is_runtime_selectable"])

    def test_candidate_sources_include_fred_for_expanded_macro_assets(self):
        examples = [
            "SOFR rose last week.",
            "WTI crude oil prices increased.",
            "HY OAS widened.",
            "EUR/USD strengthened.",
        ]

        for claim in examples:
            with self.subTest(claim=claim):
                ids = [item["source_id"] for item in candidate_sources_for_claim(claim)]
                self.assertIn("fred", ids)

    def test_candidate_sources_include_historical_prices_for_single_name_move(self):
        candidates = candidate_sources_for_claim("Qualcomm fell 6% after sharp gains on Tuesday.")
        ids = [item["source_id"] for item in candidates]

        self.assertIn("historical_prices", ids)
        self.assertNotIn("sec_company_facts", ids)
        self.assertIn("single_name_equity", candidates[0]["detected_asset_classes"])

    def test_asset_class_context_controls_price_tool_selection(self):
        equity_route = route_sources("Qualcomm fell 6% after sharp gains on Tuesday.")
        self.assertIn("single_name_equity", equity_route["asset_classes"])
        self.assertIn("historical_prices", equity_route["routes"])

        macro_route = route_sources("CPI fell 6% from a year earlier.", asset_classes=["macro_indicator"])
        self.assertIn("macro_indicator", macro_route["asset_classes"])
        self.assertNotIn("historical_prices", macro_route["routes"])
        self.assertIn("bls_api", macro_route["routes"])

        commodity_candidates = candidate_sources_for_claim(
            "WTI crude oil fell 6% after the EIA inventory report.",
            asset_classes=["commodity"],
        )
        commodity_ids = [item["source_id"] for item in commodity_candidates]
        self.assertIn("eia_api", commodity_ids)
        self.assertIn("fred", commodity_ids)
        self.assertNotIn("historical_prices", commodity_ids)

    def test_supply_amount_claim_does_not_route_to_eps_or_price_sources(self):
        candidates = candidate_sources_for_claim(
            "Nvidia said its supply rose to $119 billion in the fiscal first quarter, up from $95.2 billion the previous quarter."
        )
        ids = [item["source_id"] for item in candidates]

        self.assertNotIn("sec_company_facts", ids)
        self.assertNotIn("historical_prices", ids)
        self.assertNotIn("treasury_fiscal_data", ids)

    def test_company_product_market_claim_routes_to_discovery_not_sec_xbrl(self):
        claim = (
            'During the conference call, Huang said Nvidia\'s new "Vera" central processors '
            "give it access to a new $200 billion market."
        )
        candidates = candidate_sources_for_claim(claim)
        ids = [item["source_id"] for item in candidates]

        self.assertIn("serper_web", ids)
        self.assertNotIn("sec_company_facts", ids)
        self.assertNotIn("market_prices_vendor", ids)

    def test_selection_can_return_no_sources_when_catalog_has_no_match(self):
        selections = select_sources_for_claims(
            "The product is strategically important.",
            ToolkitConfig(),
        )

        self.assertEqual(selections[0]["selected_sources"], [])
        self.assertEqual(selections[0]["selected_provider_names"], [])
        self.assertIn("no_matching_source_candidates", selections[0]["policy_notes"])

    def test_policy_discards_unknown_and_adds_official_primary(self):
        candidates = candidate_sources_for_claim("Apple revenue grew 6% year over year.")
        validated = validate_source_selection(
            "Apple revenue grew 6% year over year.",
            candidates,
            {"selected_sources": ["made_up_source", "market_prices_vendor"]},
        )

        self.assertNotIn("made_up_source", validated["selected_sources"])
        self.assertTrue(validated["selected_sources"][0].startswith("sec_"))
        self.assertIn("discarded_unknown_source:made_up_source", validated["policy_notes"])

    def test_select_sources_fallback_returns_provider_names(self):
        selections = select_sources_for_claims(
            "Apple revenue grew 6% year over year.",
            ToolkitConfig(),
        )

        self.assertEqual(selections[0]["method"], "deterministic_fallback+detail_loaded")
        self.assertIn("sec_company_facts", selections[0]["selected_provider_names"])
        self.assertIn("sec_company_facts", selected_provider_names_from_plan(selections))
        self.assertIn("disclosure_stages", selections[0])
        self.assertTrue(selections[0]["selected_source_details"])
        self.assertEqual(
            selections[0]["disclosure_stages"]["stage_2_loaded_source_ids"],
            selections[0]["selected_sources"],
        )

    def test_selected_source_details_loads_local_markdown(self):
        detail = load_source_detail("sec_company_facts")
        planned_detail = load_source_detail("bls_api")
        details = selected_source_details(["sec_company_facts", "fred", "bls_api"])

        self.assertIn("Official docs:", detail)
        self.assertIn("Official description summary:", planned_detail)
        self.assertEqual([item["source_id"] for item in details], ["sec_company_facts", "fred", "bls_api"])
        self.assertTrue(all(item["detail_markdown"] for item in details))
        historical_detail = load_source_detail("historical_prices")
        self.assertIn("Financial Modeling Prep API playbook", historical_detail)
        self.assertIn("Symbol naming rules", historical_detail)

    def test_all_catalog_sources_have_api_playbooks(self):
        missing = []
        for entry in source_catalog(include_planned=True):
            detail = load_source_detail(entry.source_id)
            if f"Source id: {entry.source_id}" not in detail or "API playbook" not in detail:
                missing.append(entry.source_id)

        self.assertEqual(missing, [])

    def test_select_sources_tool_executes(self):
        result = execute_tool(
            "select_sources",
            {"claim": "US inflation fell last month."},
            ToolkitConfig(),
        )

        self.assertIn("selections", result)
        self.assertTrue(result["selections"][0]["selected_sources"])

    def test_select_sources_tool_can_include_planned_descriptions(self):
        result = execute_tool(
            "select_sources",
            {"claim": "BLS payroll data increased last month.", "include_planned_sources": True},
            ToolkitConfig(),
        )
        ids = [item["source_id"] for item in result["selections"][0]["candidates"]]

        self.assertIn("bls_api", ids)

    def test_select_sources_tool_skips_vague_beat_commentary(self):
        result = execute_tool(
            "select_sources",
            {
                "claim": (
                    '"Nvidia delivered another beat, but at this point that is essentially priced in '
                    'as it keeps beating quarter after quarter," said eMarketer analyst Jacob Bourne.'
                )
            },
            ToolkitConfig(),
        )

        self.assertTrue(result["skipped"])
        self.assertEqual(result["selections"], [])
        self.assertEqual(result["classification"]["argument_type"], "opinion_analysis")

    def test_free_data_source_query_filters_to_allowed_sources(self):
        client = FreeDataSourceClient(ToolkitConfig())
        calls = []

        def fake_sec_company_facts(claim, ticker, as_of_date=None):
            calls.append("sec_company_facts")
            return [SearchResult("SEC facts", "https://data.sec.gov/example")]

        def fake_sec_recent_filings(ticker, as_of_date=None):
            calls.append("sec_recent_filings")
            return [SearchResult("SEC filing", "https://www.sec.gov/example")]

        with patch.object(client, "sec_company_facts", fake_sec_company_facts), patch.object(
            client, "sec_recent_filings", fake_sec_recent_filings
        ):
            results, notes = client.query(
                claim="Apple revenue grew.",
                ticker="AAPL",
                argument_type=ArgumentType.METRIC_FACT,
                allowed_sources=["sec_company_facts"],
            )

        self.assertEqual(calls, ["sec_company_facts"])
        self.assertEqual(len(results), 1)
        self.assertEqual(notes, ["sec_company_facts: 1 result(s)"])


if __name__ == "__main__":
    unittest.main()
