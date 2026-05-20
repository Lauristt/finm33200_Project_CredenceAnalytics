import unittest

from financial_credibility.adapters import export_anthropic_tools, export_openai_tools
from financial_credibility.config import ToolkitConfig
from financial_credibility.tool_registry import all_registered_tools, get_registered_tool
from financial_credibility.tool_runtime import execute_tool


class ToolLayerTests(unittest.TestCase):
    def test_registry_contains_atomic_and_orchestrator_tools(self):
        names = {tool.name for tool in all_registered_tools()}

        self.assertIn("get_historical_prices", names)
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


if __name__ == "__main__":
    unittest.main()
