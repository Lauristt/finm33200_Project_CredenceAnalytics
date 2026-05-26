import unittest
from unittest.mock import patch

from financial_credibility.config import ToolkitConfig
from financial_credibility.data_sources import FreeDataSourceClient
from financial_credibility.models import ArgumentType, SearchResult
from financial_credibility.source_selection import (
    candidate_sources_for_claim,
    candidate_sources_for_claim_with_options,
    load_source_detail,
    select_sources_for_claims,
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

    def test_candidate_sources_can_include_planned_official_library(self):
        candidates = candidate_sources_for_claim_with_options(
            "US payroll and CPI data should be checked against BLS.",
            include_planned=True,
        )
        ids = [item["source_id"] for item in candidates]

        self.assertIn("bls_api", ids)
        self.assertTrue(any(not item["is_runtime_selectable"] for item in candidates))

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

    def test_free_data_source_query_filters_to_allowed_sources(self):
        client = FreeDataSourceClient(ToolkitConfig())
        calls = []

        def fake_sec_company_facts(claim, ticker):
            calls.append("sec_company_facts")
            return [SearchResult("SEC facts", "https://data.sec.gov/example")]

        def fake_sec_recent_filings(ticker):
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
