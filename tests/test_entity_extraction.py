import json
import tempfile
import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.asset_universe import parse_asset_universe
from financial_credibility.entity_extraction import extract_entities_from_memo
from financial_credibility.tool_runtime import execute_tool
from financial_credibility.ticker_universe import parse_ticker_universe
from unittest.mock import patch


class EntityExtractionTests(unittest.TestCase):
    def test_heuristic_extracts_known_company_tickers(self):
        result = extract_entities_from_memo(
            "Apple revenue grew while Microsoft debt declined.",
            ToolkitConfig(),
        )

        self.assertEqual(result["method"], "heuristic")
        self.assertIn("AAPL", result["tickers"])
        self.assertIn("MSFT", result["tickers"])

    def test_heuristic_extracts_inline_tickers(self):
        result = extract_entities_from_memo(
            "The memo compares $NVDA and (AMD).",
            ToolkitConfig(),
        )

        self.assertIn("NVDA", result["tickers"])
        self.assertIn("AMD", result["tickers"])

    def test_extracts_non_equity_asset_classes_without_company_tickers(self):
        result = extract_entities_from_memo(
            "CPI surprised higher while WTI, EUR/USD, S&P 500, ES futures, and HY spreads moved sharply.",
            ToolkitConfig(),
        )

        self.assertEqual(result["tickers"], [])
        self.assertIn("macro_indicator", result["asset_classes"])
        self.assertIn("commodity", result["asset_classes"])
        self.assertIn("fx", result["asset_classes"])
        self.assertIn("equity_index", result["asset_classes"])
        self.assertIn("equity_index_future", result["asset_classes"])
        self.assertIn("credit", result["asset_classes"])

    def test_manufacturing_pmi_is_macro_indicator_not_equity_ticker(self):
        result = extract_entities_from_memo(
            "Manufacturing PMI rose to 55.3 in May, its highest level since May 2022.",
            ToolkitConfig(),
        )

        self.assertEqual(result["tickers"], [])
        self.assertIn("macro_indicator", result["asset_classes"])
        self.assertIn("PMI", [entity.get("symbol") for entity in result["entities"]])

    def test_llm_public_company_pmi_is_disambiguated_to_macro_indicator(self):
        def fake_openai_entities(memo, config):
            return [
                {
                    "name": "PMI",
                    "ticker": "PMI",
                    "symbol": "PMI",
                    "entity_type": "public_company",
                    "asset_class": "single_name_equity",
                    "confidence": 0.96,
                    "source": "llm_openai",
                }
            ]

        with patch("financial_credibility.entity_extraction._openai_extract_entities", fake_openai_entities):
            result = extract_entities_from_memo(
                "Manufacturing PMI rose in May.",
                ToolkitConfig(openai_api_key="test", openai_model="test", llm_provider="openai"),
            )

        self.assertEqual(result["tickers"], [])
        self.assertIn("macro_indicator", result["asset_classes"])
        self.assertIn("PMI", [entity.get("symbol") for entity in result["entities"]])

    def test_asset_universe_filters_unrecognized_non_equity_llm_output(self):
        def fake_openai_entities(memo, config):
            return [
                {
                    "name": "Mystery Momentum Index",
                    "ticker": None,
                    "symbol": "MMX",
                    "entity_type": "index",
                    "asset_class": "equity_index",
                    "confidence": 0.96,
                    "source": "llm_openai",
                },
                {
                    "name": "Consumer Price Index",
                    "ticker": None,
                    "symbol": "CPI",
                    "entity_type": "macro_indicator",
                    "asset_class": "macro_indicator",
                    "confidence": 0.9,
                    "source": "llm_openai",
                },
            ]

        with patch("financial_credibility.entity_extraction._openai_extract_entities", fake_openai_entities):
            result = extract_entities_from_memo(
                "CPI moved while a custom momentum index moved.",
                ToolkitConfig(openai_api_key="test", openai_model="test", llm_provider="openai"),
            )

        symbols = [entity.get("symbol") for entity in result["entities"]]
        self.assertIn("CPI", symbols)
        self.assertNotIn("MMX", symbols)
        self.assertIn("filtered_asset_universe:equity_index:MMX", result["notes"])

    def test_custom_asset_universe_file_allows_local_symbols(self):
        local = {
            "assets": [
                {
                    "asset_class": "equity_index",
                    "symbol": "MMX",
                    "name": "Mystery Momentum Index",
                    "entity_type": "index",
                    "aliases": ["custom momentum index"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            file_path = f"{tmp}/asset_universe.json"
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(local, file)
            with patch(
                "financial_credibility.entity_extraction._openai_extract_entities",
                lambda memo, config: [
                    {
                        "name": "Mystery Momentum Index",
                        "ticker": None,
                        "symbol": "MMX",
                        "entity_type": "index",
                        "asset_class": "equity_index",
                        "confidence": 0.96,
                        "source": "llm_openai",
                    }
                ],
            ):
                result = extract_entities_from_memo(
                    "The custom momentum index moved.",
                    ToolkitConfig(
                        openai_api_key="test",
                        openai_model="test",
                        llm_provider="openai",
                        asset_universe_file=file_path,
                    ),
                )

        symbols = [entity.get("symbol") for entity in result["entities"]]
        self.assertIn("MMX", symbols)
        self.assertIn("asset_universe_file:", " ".join(result["notes"]))

    def test_parses_custom_asset_universe(self):
        records = parse_asset_universe(
            json.dumps(
                {
                    "assets": [
                        {
                            "asset_class": "fx",
                            "symbol": "USD/MXN",
                            "name": "USD/MXN",
                            "entity_type": "currency_pair",
                        }
                    ]
                }
            )
        )

        self.assertEqual(records[0].asset_class, "fx")
        self.assertEqual(records[0].symbol, "USD/MXN")

    def test_filters_ai_theme_when_not_explicit_ticker(self):
        result = extract_entities_from_memo(
            "Nvidia revenue growth is supported by AI infrastructure demand.",
            ToolkitConfig(),
        )

        self.assertIn("NVDA", result["tickers"])
        self.assertNotIn("AI", result["tickers"])
        self.assertIn("filtered_ambiguous_ticker:AI", result["notes"])

    def test_keeps_ai_when_explicit_ticker_context_exists(self):
        result = extract_entities_from_memo(
            "C3.ai (AI) reported revenue growth.",
            ToolkitConfig(),
        )

        self.assertIn("AI", result["tickers"])

    def test_parses_sec_company_tickers_exchange_universe(self):
        records = parse_ticker_universe(
            json.dumps(
                {
                    "fields": ["cik", "name", "ticker", "exchange"],
                    "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
                }
            )
        )

        self.assertEqual(records["AAPL"].cik, "0000320193")
        self.assertEqual(records["AAPL"].exchange, "Nasdaq")

    def test_ticker_universe_accepts_dash_dot_share_class_aliases(self):
        records = parse_ticker_universe(
            json.dumps(
                {
                    "fields": ["cik", "name", "ticker", "exchange"],
                    "data": [[1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"]],
                }
            )
        )

        self.assertEqual(records["BRK.B"].ticker, "BRK-B")

    def test_hard_filters_unlisted_ticker_candidates_after_extraction(self):
        universe = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1045810, "NVIDIA CORP", "NVDA", "Nasdaq"]],
        }
        with tempfile.TemporaryDirectory() as tmp:
            file_path = f"{tmp}/ticker_universe.json"
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(universe, file)
            result = extract_entities_from_memo(
                "NVDA revenue grew while ABCD remained speculative.",
                ToolkitConfig(ticker_universe_file=file_path),
            )

        self.assertEqual(result["tickers"], ["NVDA"])
        self.assertIn("filtered_unlisted_ticker:ABCD", result["notes"])
        self.assertEqual(result["entities"][0]["cik"], "0001045810")
        self.assertEqual(result["entities"][0]["exchange"], "Nasdaq")

    def test_extract_entities_tool_executes(self):
        result = execute_tool(
            "extract_entities",
            {"memo": "Tesla margins improved but Netflix revenue slowed."},
            ToolkitConfig(),
        )

        self.assertIn("TSLA", result["tickers"])
        self.assertIn("NFLX", result["tickers"])


if __name__ == "__main__":
    unittest.main()
