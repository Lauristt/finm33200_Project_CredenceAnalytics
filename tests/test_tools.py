import unittest
from datetime import date
from unittest.mock import patch

from financial_credibility.adapters import export_anthropic_tools, export_openai_response_tools, export_openai_tools
from financial_credibility.config import ToolkitConfig
from financial_credibility.price_history import PricePoint
from financial_credibility.tool_profiles import tool_names_for_profile
from financial_credibility.tool_registry import all_registered_tools, get_registered_tool
from financial_credibility.tool_runtime import execute_tool


class ToolLayerTests(unittest.TestCase):
    def test_registry_contains_atomic_and_orchestrator_tools(self):
        names = {tool.name for tool in all_registered_tools()}

        self.assertIn("get_historical_prices", names)
        self.assertIn("load_source_documentation", names)
        self.assertIn("verify_logic_claim", names)
        self.assertIn("build_evidence_pack", names)
        self.assertEqual(get_registered_tool("classify_claim").requires_keys, [])

    def test_adapters_export_provider_schemas(self):
        openai_tools = export_openai_tools()
        anthropic_tools = export_anthropic_tools()

        self.assertGreaterEqual(len(openai_tools), 10)
        self.assertEqual(openai_tools[0]["type"], "function")
        self.assertIn("function", openai_tools[0])
        self.assertIn("input_schema", anthropic_tools[0])

    def test_tool_profiles_keep_default_surface_narrow(self):
        core = tool_names_for_profile("agent_core")
        deep = tool_names_for_profile("retrieval_deep")
        review = tool_names_for_profile("review")

        self.assertIn("retrieve_evidence", core)
        self.assertIn("load_source_documentation", core)
        self.assertIn("get_sec_company_facts", deep)
        self.assertNotIn("build_evidence_pack", core)
        self.assertEqual(review, ["summarize_evidence_pack", "summarize_audit_report", "review_tool_surface"])

    def test_response_schemas_include_guidance_and_non_strict_functions(self):
        tools = export_openai_response_tools("agent_core")
        descriptions = {tool["name"]: tool["description"] for tool in tools}

        self.assertTrue(all(tool["strict"] is False for tool in tools))
        self.assertIn("Use when:", descriptions["retrieve_evidence"])
        self.assertIn("Do not use when:", descriptions["retrieve_evidence"])
        self.assertIn("Recommended next tools:", descriptions["retrieve_evidence"])
        self.assertIn("endpoint schemas", descriptions["load_source_documentation"])
        self.assertNotIn("build_evidence_pack", descriptions)

    def test_execute_load_source_documentation_returns_api_playbook(self):
        result = execute_tool(
            "load_source_documentation",
            {"source_ids": ["historical_prices", "market_prices_vendor"]},
            ToolkitConfig(),
        )

        self.assertEqual(result["missing_source_ids"], [])
        docs = "\n".join(item["detail_markdown"] for item in result["details"])
        self.assertIn("Financial Modeling Prep API playbook", docs)
        self.assertIn("FMP_API_KEY", docs)
        self.assertIn("^GSPC", docs)

    def test_execute_classify_claim(self):
        result = execute_tool(
            "classify_claim",
            {"claim": "Nvidia's stock price seems like oscillating over 10 months."},
            ToolkitConfig(),
        )

        self.assertEqual(result["argument_type"], "opinion_analysis")
        self.assertIn("price action pattern", result["signals"])

    def test_execute_retrieve_and_verify_numeric_with_prefetched_evidence(self):
        retrieved = execute_tool(
            "retrieve_evidence",
            {
                "claim": "Apple revenue grew 6% year over year.",
                "ticker": "AAPL",
                "as_of_date": "2025-11-01",
                "prefetched_results": [
                    {
                        "title": "Apple reports results",
                        "url": "https://www.apple.com/newsroom/example",
                        "snippet": "Revenue grew 6 percent year over year.",
                        "published_at": "2025-10-30",
                    }
                ],
            },
            ToolkitConfig(),
        )
        numeric = execute_tool(
            "verify_numeric_claim",
            {
                "claim": "Apple revenue grew 6% year over year.",
                "evidence": retrieved["evidence"],
            },
            ToolkitConfig(),
        )

        self.assertEqual(retrieved["argument_type"], "metric_fact")
        self.assertEqual(numeric["verdict"], "verified")

    def test_retrieve_and_verify_skip_forecast_or_opinion_claims(self):
        retrieved = execute_tool(
            "retrieve_evidence",
            {
                "claim": "Nvidia revenue could accelerate into 2027.",
                "ticker": "NVDA",
                "prefetched_results": [
                    {
                        "title": "SEC Company Facts for NVDA",
                        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json",
                        "snippet": "Revenues (USD) 2026 Q1: 81620000000 filed 2026-05-20 form 10-Q",
                        "source": "SEC EDGAR",
                    }
                ],
            },
            ToolkitConfig(),
        )
        verified = execute_tool(
            "verify_atomic_claim",
            {
                "claim": "Intel has a weak AI moat versus competing silicon.",
                "ticker": "INTC",
                "evidence": [],
                "canonical_facts": [],
            },
            ToolkitConfig(),
        )

        self.assertTrue(retrieved["skipped"])
        self.assertEqual(retrieved["evidence"], [])
        self.assertTrue(verified["skipped"])
        self.assertEqual(verified["atomic_claims"][0]["verdict"], "not_applicable")

    def test_retrieve_skips_investor_reassurance_framing(self):
        retrieved = execute_tool(
            "retrieve_evidence",
            {
                "claim": (
                    "Nvidia CEO Jensen Huang aimed to assure investors that the world's most valuable "
                    "company can keep up its blockbuster growth with the help of a broad base of customers."
                ),
                "ticker": "NVDA",
                "prefetched_results": [
                    {
                        "title": "SEC Company Facts for NVDA",
                        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json",
                        "snippet": "Revenues (USD) 2026 Q1: 81620000000 filed 2026-05-20 form 10-Q",
                        "source": "SEC EDGAR",
                    }
                ],
            },
            ToolkitConfig(),
        )

        self.assertTrue(retrieved["skipped"])
        self.assertEqual(retrieved["classification"]["argument_type"], "opinion_analysis")
        self.assertEqual(retrieved["evidence"], [])

    def test_execute_build_evidence_pack_with_prefetched_results(self):
        result = execute_tool(
            "build_evidence_pack",
            {
                "claim": "Apple revenue grew 6% year over year.",
                "ticker": "AAPL",
                "as_of_date": "2025-11-01",
                "prefetched_results": [
                    {
                        "title": "Apple reports results",
                        "url": "https://www.apple.com/newsroom/example",
                        "snippet": "Revenue grew 6 percent year over year.",
                        "published_at": "2025-10-30",
                    }
                ],
            },
            ToolkitConfig(),
        )

        self.assertEqual(result["mode"], "agentic")
        self.assertIn("numeric_check", result)
        self.assertEqual(result["numeric_check"]["verdict"], "verified")

    def test_execute_review_and_audit_tools(self):
        review = execute_tool("review_tool_surface", {"profile": "agent_core"}, ToolkitConfig())
        audit = execute_tool(
            "audit_verification_chain",
            {
                "agent_trace": {
                    "run_id": "trace_1",
                    "tool_profile": "all",
                    "tool_calls": [],
                }
            },
            ToolkitConfig(),
        )

        self.assertEqual(review["profile"], "agent_core")
        self.assertGreater(review["tool_count"], 1)
        self.assertIn("tool_surface", {finding["category"] for finding in audit["findings"]})

    def test_get_historical_prices_passes_parameters_to_provider(self):
        calls = {}

        class FakeDataSourceClient:
            def __init__(self, config):
                calls["config"] = config

            def alpha_vantage_historical_prices(self, ticker, start, end):
                calls["alpha_vantage_args"] = (ticker, start, end)
                return [
                    PricePoint(date(2025, 1, 2), 100.0, 105.0, 99.0, 100.0, 1000),
                    PricePoint(date(2025, 1, 3), 104.0, 108.0, 103.0, 107.0, 1200),
                ]

            def fmp_historical_prices(self, ticker, start, end):
                raise AssertionError("FMP should not be called after Alpha Vantage succeeds")

            def finnhub_historical_prices(self, ticker, start, end):
                raise AssertionError("Finnhub should not be called after Alpha Vantage succeeds")

            def stooq_historical_prices(self, ticker, start, end):
                raise AssertionError("Stooq should not be called after Alpha Vantage succeeds")

            def _price_history_url(self, provider_name, ticker, start, end):
                calls["url_args"] = (provider_name, ticker, start, end)
                return "https://example.com/prices"

        config = ToolkitConfig(alpha_vantage_api_key="test-key")
        with patch("financial_credibility.tool_runtime.FreeDataSourceClient", FakeDataSourceClient):
            result = execute_tool(
                "get_historical_prices",
                {
                    "ticker": "msft",
                    "start_date": "2025-01-02",
                    "end_date": "2025-01-03",
                },
                config,
            )

        self.assertIs(calls["config"], config)
        self.assertEqual(calls["alpha_vantage_args"], ("msft", date(2025, 1, 2), date(2025, 1, 3)))
        self.assertEqual(calls["url_args"], ("alpha_vantage_historical_prices", "msft", date(2025, 1, 2), date(2025, 1, 3)))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ticker"], "MSFT")
        self.assertEqual(result["provider"], "Alpha Vantage")
        self.assertEqual(result["summary"]["observations"], 2)

    def test_build_evidence_pack_strict_mode_passes_arguments_to_toolkit(self):
        calls = {}

        class FakePack:
            def to_dict(self):
                return {"status": "ok"}

        class FakeToolkit:
            def __init__(self, config):
                calls["config"] = config

            def build_evidence_pack(self, **kwargs):
                calls["build_kwargs"] = kwargs
                return FakePack()

        prefetched = [
            {
                "title": "Microsoft report",
                "url": "https://example.com/msft",
                "snippet": "Revenue was strong.",
            }
        ]
        config = ToolkitConfig()
        with patch("financial_credibility.tool_runtime.FinancialCredibilityToolkit", FakeToolkit):
            result = execute_tool(
                "build_evidence_pack",
                {
                    "claim": "Microsoft performed well.",
                    "ticker": "MSFT",
                    "as_of_date": "2026-05-20",
                    "max_sources": 3,
                    "mode": "strict",
                    "prefetched_results": prefetched,
                },
                config,
            )

        self.assertIs(calls["config"], config)
        self.assertEqual(
            calls["build_kwargs"],
            {
                "claim": "Microsoft performed well.",
                "ticker": "MSFT",
                "as_of_date": "2026-05-20",
                "max_sources": 3,
                "prefetched_results": prefetched,
                "mode": "strict",
            },
        )
        self.assertEqual(result, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
