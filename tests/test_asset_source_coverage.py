import unittest

from financial_credibility.asset_source_map import (
    asset_source_plan,
    data_sources_for_asset_class,
    describe_data_sources,
    series_mappings_for_claim,
)
from financial_credibility.config import ToolkitConfig
from financial_credibility.entity_extraction import extract_entities_from_memo
from financial_credibility.facts import canonicalize_search_results
from financial_credibility.models import SearchResult
from financial_credibility.routing import route_sources
from financial_credibility.source_selection import candidate_sources_for_claim_with_options
from financial_credibility.tool_runtime import execute_tool


NEWS_SEEDED_COVERAGE_CASES = [
    {
        "claim": "Nvidia shares rallied after investors focused on AI demand and its revenue outlook.",
        "asset_classes": {"single_name_equity"},
        "sources": {"sec_company_facts", "sec_recent_filings", "historical_prices"},
        "series_ids": {"us-gaap concept map", "ticker OHLCV"},
    },
    {
        "claim": "The S&P 500 closed at a record high while the Nasdaq also rose.",
        "asset_classes": {"equity_index"},
        "sources": {"historical_prices", "market_prices_vendor"},
        "series_ids": {"index OHLCV"},
    },
    {
        "claim": "US core CPI inflation cooled in the latest BLS report.",
        "asset_classes": {"macro_indicator"},
        "sources": {"bls_api", "fred"},
        "series_ids": {"CUSR0000SA0L1E"},
    },
    {
        "claim": "US GDP and PCE inflation data should be checked against BEA.",
        "asset_classes": {"macro_indicator"},
        "sources": {"bea_api", "fred"},
        "series_ids": {"NIPA T10101 line 1", "NIPA T20804 line 1"},
    },
    {
        "claim": "The 30-year Treasury yield rose as rates markets sold off.",
        "asset_classes": {"rates"},
        "sources": {"fred"},
        "series_ids": {"DGS30"},
    },
    {
        "claim": "High-yield OAS tightened while investment-grade corporate bond spreads were stable.",
        "asset_classes": {"credit"},
        "sources": {"fred"},
        "series_ids": {"BAMLH0A0HYM2", "BAMLC0A0CM"},
    },
    {
        "claim": "WTI crude oil rose after EIA data showed lower crude stockpiles.",
        "asset_classes": {"commodity"},
        "sources": {"eia_api", "fred"},
        "series_ids": {"RWTC", "WCESTUS1"},
    },
    {
        "claim": "Gold futures open interest increased in the latest CFTC COT data.",
        "asset_classes": {"commodity", "derivatives"},
        "sources": {"cftc_cot", "fred"},
        "series_ids": {"CFTC PRE 6dca-aqww", "GOLDAMGBD228NLBM"},
    },
    {
        "claim": "The dollar strengthened against the yen as Treasury yields rose.",
        "asset_classes": {"fx", "rates"},
        "sources": {"fred"},
        "series_ids": {"DEXJPUS", "DGS10"},
    },
    {
        "claim": "FINRA TRACE corporate bond trading volumes increased.",
        "asset_classes": {"fixed_income"},
        "sources": {"finra_query_api"},
        "series_ids": {"FINRA group/name dataset"},
    },
    {
        "claim": "IMF WEO projected US GDP growth to improve.",
        "asset_classes": {"macro_indicator"},
        "sources": {"imf_data_api"},
        "series_ids": {"WEO country.indicator.frequency key"},
    },
    {
        "claim": "World Bank China GDP data from 2015 to 2023 should use WDI.",
        "asset_classes": {"macro_indicator"},
        "sources": {"world_bank_indicators"},
        "series_ids": {"NY.GDP.MKTP.CD / indicator id"},
    },
    {
        "claim": "The Bank of England Bank Rate remained unchanged while sterling moved.",
        "asset_classes": {"rates", "fx"},
        "sources": {"bank_of_england"},
        "series_ids": {"IUDBEDR / IUDSOIA"},
    },
    {
        "claim": "The ECB deposit facility rate and euro reference rates are official ECB data.",
        "asset_classes": {"rates", "fx"},
        "sources": {"ecb_data_portal"},
        "series_ids": {"FM SDMX policy-rate key", "EXR SDMX key"},
    },
]


class AssetSourceCoverageTests(unittest.TestCase):
    def test_data_source_descriptions_cover_major_asset_classes(self):
        descriptions = describe_data_sources()
        by_source = {item["source_id"]: item for item in descriptions}

        for source_id in [
            "sec_company_facts",
            "fred",
            "bls_api",
            "bea_api",
            "eia_api",
            "cftc_cot",
            "finra_query_api",
            "ecb_data_portal",
            "bis_data_portal",
            "imf_data_api",
            "world_bank_indicators",
            "bank_of_england",
            "openfigi",
        ]:
            with self.subTest(source_id=source_id):
                self.assertIn(source_id, by_source)
                self.assertTrue(by_source[source_id]["data_available"])
                self.assertTrue(by_source[source_id]["identifiers"])

        for asset_class in [
            "single_name_equity",
            "commodity",
            "credit",
            "fx",
            "rates",
            "fixed_income",
            "derivatives",
            "macro_indicator",
        ]:
            with self.subTest(asset_class=asset_class):
                self.assertTrue(data_sources_for_asset_class(asset_class, include_planned=True))

    def test_news_seeded_claims_map_to_asset_sources_and_series(self):
        config = ToolkitConfig(enable_ticker_universe_filter=False)

        for case in NEWS_SEEDED_COVERAGE_CASES:
            with self.subTest(claim=case["claim"]):
                extraction = extract_entities_from_memo(case["claim"], config)
                extracted_assets = set(extraction["asset_classes"])
                plan = asset_source_plan(case["claim"], extraction["entities"], include_planned=True)
                candidates = candidate_sources_for_claim_with_options(case["claim"], top_k=12, include_planned=True)
                route_ids = set(route_sources(case["claim"], official_only=False)["routes"])
                mapped_series = {item["source_series_id"] for item in plan["series_mappings"]}
                candidate_ids = {item["source_id"] for item in candidates}
                source_ids = set(plan["source_ids"]) | candidate_ids | route_ids

                self.assertTrue(case["asset_classes"] <= set(plan["asset_classes"]) | extracted_assets)
                self.assertTrue(case["sources"] <= source_ids)
                self.assertTrue(case["series_ids"] <= mapped_series)

    def test_map_asset_sources_tool_exposes_planning_payload(self):
        result = execute_tool(
            "map_asset_sources",
            {"claim": "WTI crude oil rose after EIA reported lower crude stockpiles."},
            ToolkitConfig(eia_api_key="test", fred_api_key="test", enable_ticker_universe_filter=False),
        )

        self.assertIn("commodity", result["asset_classes"])
        self.assertIn("eia_api", result["source_ids"])
        self.assertIn("RWTC", {item["source_series_id"] for item in result["series_mappings"]})
        self.assertIn("WCESTUS1", {item["source_series_id"] for item in result["series_mappings"]})

    def test_asset_source_plan_keeps_claim_sources_separate_from_generic_asset_sources(self):
        config = ToolkitConfig(enable_ticker_universe_filter=False)
        claim = "Nvidia supply rose to $119 billion in the fiscal first quarter."
        extraction = extract_entities_from_memo(claim, config)
        plan = asset_source_plan(claim, extraction["entities"], include_planned=False)

        self.assertIn("single_name_equity", plan["asset_classes"])
        self.assertEqual(plan["source_ids"], [])
        self.assertIn("sec_company_facts", plan["available_source_ids"])
        self.assertIn("historical_prices", plan["available_source_ids"])

    def test_structured_provider_rows_canonicalize_to_observation_facts(self):
        result = SearchResult(
            title="BLS CPI (CUSR0000SA0)",
            url="https://www.bls.gov/developers/",
            snippet="2026-M04: 319.1; 2026-M03: 318.8",
            source="BLS Public Data API",
            raw={
                "provider": "bls_api",
                "series_id": "CUSR0000SA0",
                "rows": [
                    {"date": "2026-M04", "value": "319.1", "year": "2026", "period": "M04"},
                    {"date": "2026-M03", "value": "318.8", "year": "2026", "period": "M03"},
                ],
            },
        )

        facts = canonicalize_search_results([result], "MACRO")

        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0].fact_name, "CUSR0000SA0")
        self.assertEqual(facts[0].observation_date, "2026-M04")
        self.assertEqual(facts[0].value, 319.1)

    def test_series_mapping_filter_can_hide_planned_sources(self):
        visible = series_mappings_for_claim(
            "FINRA TRACE corporate bond trading volumes increased.",
            ["fixed_income"],
            include_planned=True,
        )
        runtime_only = series_mappings_for_claim(
            "FINRA TRACE corporate bond trading volumes increased.",
            ["fixed_income"],
            include_planned=False,
        )

        self.assertIn("finra_query_api", {item["source_id"] for item in visible})
        self.assertIn("finra_query_api", {item["source_id"] for item in runtime_only})


if __name__ == "__main__":
    unittest.main()
