import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from financial_credibility.batch import run_batch
from financial_credibility.config import ToolkitConfig
from financial_credibility.errors import UserFacingError


class _FakePack:
    def __init__(self, ticker, prefetched_results=None):
        self.ticker = ticker
        self.prefetched_results = prefetched_results

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "verdict": "supported",
            "credibility_score": 0.8,
            "overall_conclusion": {"overall_label": "High", "final_confidence": 0.82},
            "numeric_check": {"verdict": "verified"},
            "source_check": {"verdict": "verified"},
            "atomic_claims": [
                {"human_review_required": False, "review_reasons": []}
            ],
            "evidence": [{"is_official_primary": True}],
            "prefetched_count": len(self.prefetched_results or []),
        }


class _FakeToolkit:
    def __init__(self, config):
        self.config = config

    def build_evidence_pack(self, **kwargs):
        if kwargs["ticker"] == "FAIL":
            raise RuntimeError("forced failure")
        return _FakePack(kwargs["ticker"], kwargs.get("prefetched_results"))


class BatchTests(unittest.TestCase):
    def test_batch_runner_processes_csv_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["claim", "ticker", "mode"])
                writer.writeheader()
                writer.writerow({"claim": "Apple revenue grew.", "ticker": "AAPL", "mode": "strict"})

            with patch("financial_credibility.batch.FinancialCredibilityToolkit", _FakeToolkit):
                result = run_batch(path, ToolkitConfig(), {"mode": "strict"})

        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertEqual(result["results"][0]["result"]["ticker"], "AAPL")
        self.assertEqual(result["summary"]["numeric_check_counts"], {"verified": 1})
        self.assertEqual(result["summary"]["source_check_counts"], {"verified": 1})
        self.assertEqual(result["summary"]["official_source_count"], 1)
        self.assertEqual(result["summary"]["average_credibility_score"], 0.8)

    def test_batch_runner_collects_errors_without_stopping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["claim", "ticker", "mode"])
                writer.writeheader()
                writer.writerow({"claim": "Bad row.", "ticker": "FAIL", "mode": "strict"})
                writer.writerow({"claim": "Apple revenue grew.", "ticker": "AAPL", "mode": "strict"})

            with patch("financial_credibility.batch.FinancialCredibilityToolkit", _FakeToolkit):
                result = run_batch(path, ToolkitConfig(), {"mode": "strict"})

        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["summary"]["succeeded"], 1)

    def test_batch_demo_preset_marks_rows_and_uses_prefetched_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["claim", "ticker", "mode"])
                writer.writeheader()
                writer.writerow({"claim": "Apple revenue grew.", "ticker": "AAPL", "mode": "strict"})

            with patch("financial_credibility.batch.FinancialCredibilityToolkit", _FakeToolkit):
                result = run_batch(path, ToolkitConfig(), {"mode": "strict", "demo_preset": "equity_supported"})

        row = result["results"][0]["result"]
        self.assertTrue(row["demo_mode"])
        self.assertEqual(row["demo_preset"], "equity_supported")
        self.assertGreater(row["prefetched_count"], 0)

    def test_batch_missing_required_column_reports_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            path.write_text("claim\nApple revenue grew.\n", encoding="utf-8")

            with self.assertRaises(UserFacingError) as ctx:
                run_batch(path, ToolkitConfig())

        self.assertEqual(ctx.exception.code, "batch_input_missing_columns")


if __name__ == "__main__":
    unittest.main()
