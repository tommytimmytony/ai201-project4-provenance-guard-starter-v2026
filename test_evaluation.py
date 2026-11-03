"""Focused regression checks for complete, honest evaluation reports."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import config
import run_attacks
import run_eval
import scenarios


class EvaluationTests(unittest.TestCase):
    def test_missing_criterion_is_rejected(self):
        self.assertEqual(scenarios.validate(), [])
        with patch.object(scenarios, "SCENARIOS", scenarios.SCENARIOS[:4]):
            self.assertIn(
                "provide exactly one scenario for each of the five unchanged criteria",
                scenarios.validate(),
            )

    def test_rejection_status_without_log_is_a_miss(self):
        with patch.object(scenarios, "log_entries", side_effect=[[], []]), patch.object(
            scenarios, "send", return_value=(400, {"error": "invalid_text"}),
        ):
            result = scenarios.rejection_check("http://local", 1, [], [({"json": {}}, 400)])
        self.assertEqual(result["measurement"], "1/1")
        self.assertFalse(result["met"])
        self.assertFalse(result["rejections_logged"])

    def test_one_failed_trial_makes_the_overall_verdict_missed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            config, "RESULTS_DIR", Path(directory),
        ), patch.object(config, "ROOT", Path(directory)):
            checks = [
                {"measurement": value, "met": met, "records": []}
                for value, met in [(0.31, True), (0.29, False), (0.31, True)]
            ]
            run_eval.write_report([{
                "scenario": scenarios.SCENARIOS[0], "checks": checks,
                "trials": [[], [], []],
            }], SimpleNamespace(trials=3, label="before"))
            report = next(Path(directory).glob("*.md")).read_text(encoding="utf-8")
            self.assertIn("| 0.31 | 0.29 | 0.31 | MISSED |", report)
            data = json.loads(next(Path(directory).glob("*.json")).read_text(encoding="utf-8"))
            self.assertFalse(data["rows"][0]["checks"][1]["met"])

    def test_attack_table_uses_combined_score_not_confidence(self):
        row = {
            "id": "EV01", "family": "evasion", "targets": "human label",
            "status": 200, "content_id": "example", "guess": "unsure",
            "combined_score": 0.45, "confidence": 0.10, "verdict": "", "note": "",
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            config, "RESULTS_DIR", Path(directory),
        ), patch.object(config, "ROOT", Path(directory)):
            run_attacks.write_report(
                [row], SimpleNamespace(label="before", folder="local_attacks"),
            )
            report = next(Path(directory).glob("*.md")).read_text(encoding="utf-8")
            self.assertIn("| unsure | 0.450 |", report)


if __name__ == "__main__":
    unittest.main()
