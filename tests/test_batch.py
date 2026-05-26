import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from financial_credibility.batch import run_batch
from financial_credibility.config import ToolkitConfig
from financial_credibility.errors import UserFacingError


class _FakePack:
    def __init__(self, ticker):
        self.ticker = ticker

    def to_dict(self):
        return {"ticker": self.ticker, "verdict": "supported"}


class _FakeToolkit:
    def __init__(self, config):
        self.config = config

    def build_evidence_pack(self, **kwargs):
        if kwargs["ticker"] == "FAIL":
            raise RuntimeError("forced failure")
        return _FakePack(kwargs["ticker"])


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

    def test_batch_missing_required_column_reports_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            path.write_text("claim\nApple revenue grew.\n", encoding="utf-8")

            with self.assertRaises(UserFacingError) as ctx:
                run_batch(path, ToolkitConfig())

        self.assertEqual(ctx.exception.code, "batch_input_missing_columns")


if __name__ == "__main__":
    unittest.main()
