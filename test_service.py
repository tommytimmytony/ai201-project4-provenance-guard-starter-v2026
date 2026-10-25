"""Offline regression tests. Model inference is mocked; the demo uses real GPT-2."""

import importlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
import audit
import config
import detector
import scoring
import stylometry


class StyleTests(unittest.TestCase):
    def test_empty_and_one_sentence(self):
        for text in ("", "   ", "One short sentence."):
            self.assertEqual(stylometry.sentence_length_spread(text), 0)
            self.assertEqual(stylometry.style_signal(text), 0.5)
        self.assertEqual(stylometry.type_token_ratio(""), 0)
        self.assertEqual(stylometry.punctuation_density(""), 0)

    def test_known_measures(self):
        self.assertEqual(stylometry.type_token_ratio("Red red blue blue"), 0.5)
        self.assertEqual(stylometry.punctuation_density("Hi!"), 1 / 3)
        self.assertEqual(stylometry.sentence_length_spread("One two. Three four."), 0)
        self.assertGreater(stylometry.sentence_length_spread("Go. Here are four words."), 0)

    def test_style_varies_and_stays_bounded(self):
        samples = [
            "The system provides reliable results for every user. " * 5,
            "Stop! I lugged my dented kettle uphill, past briars, shouting: 'Why today?' "
            "Nobody answered; dusk bruised the ridge. Fine. "
            "We camped beside a crooked fence, counted twelve moths, and forgot the tea.",
        ]
        scores = [stylometry.style_signal(text) for text in samples]
        self.assertNotEqual(*scores)
        self.assertTrue(all(0 <= score <= 1 for score in scores))


class ScoringTests(unittest.TestCase):
    def test_average_and_disagreement(self):
        self.assertEqual(scoring.combine_signals(0.7, 0.9), 0.8)
        self.assertEqual(scoring.combine_signals(0.1, 0.9), 0.5)
        self.assertEqual(scoring.combine_signals(0.25, 0.75), 0.5)

    def test_label_boundaries(self):
        for value, expected in (
            (0, "human"), (0.35, "human"), (0.3501, "unsure"),
            (0.6499, "unsure"), (0.65, "ai"), (1, "ai"),
        ):
            with self.subTest(score=value):
                self.assertEqual(scoring.score_to_label(value)[0], expected)

    def test_invalid_scores(self):
        for value in (-1, 2, math.inf, math.nan):
            with self.subTest(score=value), self.assertRaises(ValueError):
                scoring.combine_signals(value, 0.5)
            with self.subTest(score=value), self.assertRaises(ValueError):
                scoring.score_to_label(value)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        log_dir = Path(self.directory.name)
        for name, value in (("LOG_DIR", log_dir), ("AUDIT_LOG", log_dir / "audit.jsonl")):
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = app.app.test_client()

    def submit(self):
        with patch.object(detector, "model_signal", return_value=0.8):
            return self.client.post("/submit", json={
                "text": "This sample contains enough words to be scored.",
                "creator_id": " writer ",
            })

    def test_successful_submission_is_logged(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "decided")
        for field in ("model_score", "style_score", "combined_score", "confidence"):
            self.assertTrue(0 <= body[field] <= 1)
        entry = audit.read_entries()[0]
        self.assertEqual(entry["content_id"], body["content_id"])
        self.assertEqual(entry["creator_id"], "writer")
        self.assertEqual(entry["combined_score"], body["combined_score"])
        log = self.client.get("/log?limit=1").get_json()
        self.assertEqual(log["entries"], [entry])

    def test_ids_are_unique(self):
        self.assertNotEqual(self.submit().get_json()["content_id"], self.submit().get_json()["content_id"])

    def test_bad_submit_bodies_do_not_call_model(self):
        bodies = [
            {}, [], None, "text", {"text": None}, {"text": 123},
            {"text": ""}, {"text": "   "}, {"text": "three valid words"},
            {"text": "three valid words", "creator_id": []},
            {"text": "three valid words", "creator_id": " "},
            {"text": "three valid words", "creator_id": "x" * 101},
        ]
        with patch.object(detector, "model_signal") as model:
            for body in bodies:
                with self.subTest(body=body):
                    response = self.client.post(
                        "/submit", data=json.dumps(body), content_type="application/json",
                    )
                    self.assertEqual(response.status_code, 400)
            model.assert_not_called()
        self.assertEqual(len(audit.read_entries()), len(bodies))

    def test_encoding_and_size_errors(self):
        cases = [
            ({"data": "{", "content_type": "application/json"}, 400),
            ({"data": "hello"}, 415),
            ({"json": {"text": "hi", "creator_id": "writer"}}, 422),
            ({"json": {"text": "x " * 5001, "creator_id": "writer"}}, 413),
            ({"data": "x" * 65537, "content_type": "application/json"}, 413),
        ]
        with patch.object(detector, "model_signal") as model:
            for kwargs, expected in cases:
                with self.subTest(expected=expected, kwargs=str(kwargs)[:100]):
                    response = self.client.post("/submit", **kwargs)
                    self.assertEqual(response.status_code, expected)
                    self.assertIn("error", response.get_json())
            model.assert_not_called()
        self.assertTrue(all(entry["status"] == "rejected" for entry in audit.read_entries()))

    def test_model_failure_is_not_a_decision(self):
        with self.assertLogs(app.app.logger, level="ERROR"):
            for exception, expected in (
                (detector.DetectorUnavailable("not loaded"), 503),
                (ValueError("too few tokens"), 422),
            ):
                with patch.object(detector, "model_signal", side_effect=exception):
                    response = self.client.post("/submit", json={
                        "text": "three valid words", "creator_id": "writer",
                    })
                    self.assertEqual(response.status_code, expected)
        self.assertTrue(all(entry["status"] == "rejected" for entry in audit.read_entries()))

    def test_appeal_preserves_original_and_appends_status(self):
        content_id = self.submit().get_json()["content_id"]
        original = audit.read_entries()[0]
        response = self.client.post("/appeal", json={
            "content_id": content_id, "reasoning": "Please review this decision.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "under_review")
        entries = audit.entries_for(content_id)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0], original)
        self.assertEqual(entries[-1]["creator_id"], "writer")
        self.assertEqual(entries[-1]["status"], "under_review")

    def test_invalid_appeals(self):
        for body, status in (
            ({}, 400),
            ({"content_id": [], "reasoning": "please"}, 400),
            ({"content_id": "unknown", "reasoning": ""}, 400),
            ({"content_id": "unknown", "reasoning": 3}, 400),
            ({"content_id": "unknown", "reasoning": "x" * 2001}, 400),
            ({"content_id": "unknown", "reasoning": "please review"}, 404),
        ):
            with self.subTest(body=str(body)[:100]):
                self.assertEqual(self.client.post("/appeal", json=body).status_code, status)
        self.assertFalse(any(entry.get("event") == "appeal" for entry in audit.read_entries()))

    def test_log_failure_does_not_confirm_success(self):
        with patch.object(audit, "log_decision", side_effect=OSError("disk full")):
            with patch.dict(app.app.config, {"TESTING": False}), self.assertLogs(
                app.app.logger, level="ERROR",
            ):
                self.assertEqual(self.submit().status_code, 500)

    def test_limiter_enabled_records_rejections(self):
        try:
            with patch.dict(os.environ, {"AI201_RATE_LIMITS": "1"}):
                importlib.reload(config)
                # Reloading config resets the temporary log path, so restore it here.
                config.LOG_DIR = Path(self.directory.name)
                config.AUDIT_LOG = config.LOG_DIR / "audit.jsonl"
                importlib.reload(app)
                client = app.app.test_client()
                with patch.object(detector, "model_signal", return_value=0.5):
                    statuses = [
                        client.post("/submit", json={
                            "text": "three valid words", "creator_id": "flood",
                        }).status_code
                        for _ in range(15)
                    ]
                self.assertEqual(statuses, [200] * 10 + [429] * 5)
                self.assertEqual(sum(e.get("reason") == "rate_limited" for e in audit.read_entries()), 5)
        finally:
            importlib.reload(config)
            importlib.reload(app)


if __name__ == "__main__":
    unittest.main()
