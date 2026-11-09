"""Offline tests for the hosted capstone runner."""

import unittest
from unittest.mock import patch

import run_capstone


class FakeResponse:
    def __init__(self, status_code, body=None, text=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else ""
        self.headers = headers or {}

    def json(self):
        return self._body


class CapstoneRunnerTests(unittest.TestCase):
    def test_health_trial_requires_ok_true(self):
        with patch.object(
            run_capstone, "request",
            return_value=(FakeResponse(200, {"ok": True}), 12.5),
        ):
            result = run_capstone.health_trial()
        self.assertTrue(result["passed"])
        self.assertEqual(result["duration_ms"], 12.5)

        with patch.object(
            run_capstone, "request",
            return_value=(FakeResponse(200, {"ok": False}), 8.0),
        ):
            self.assertFalse(run_capstone.health_trial()["passed"])

    def test_unauthorized_trial_rejects_protected_data(self):
        with patch.object(
            run_capstone, "request",
            return_value=(FakeResponse(401, {"error": "unauthorized"}), 3.0),
        ):
            self.assertTrue(run_capstone.unauthorized_trial("/log")["passed"])

        with patch.object(
            run_capstone, "request",
            return_value=(FakeResponse(401, {"entries": []}), 3.0),
        ):
            self.assertFalse(run_capstone.unauthorized_trial("/log")["passed"])

    def test_method_error_rejects_stack_trace(self):
        with patch.object(
            run_capstone, "request",
            return_value=(FakeResponse(405, text="Method Not Allowed"), 4.0),
        ):
            self.assertTrue(run_capstone.method_error_trial()["passed"])

        with patch.object(
            run_capstone, "request",
            return_value=(FakeResponse(405, text="Method Not Allowed\nTraceback"), 4.0),
        ):
            self.assertFalse(run_capstone.method_error_trial()["passed"])

    def test_sensitive_data_trials_find_unredacted_value(self):
        responses = []
        for index in range(1, 4):
            responses.extend([
                (FakeResponse(200, {"status": "decided"}), 100.0),
                (FakeResponse(200, text="{}"), 2.0),
                (FakeResponse(
                    200,
                    text="dummy-api-key-capstone-2" if index == 2 else "{}",
                ), 2.0),
            ])

        with patch.object(run_capstone, "LOG_TOKEN", "review-secret"), patch.object(
            run_capstone, "request", side_effect=responses,
        ):
            trials = run_capstone.sensitive_data_trials()

        self.assertEqual(len(trials), 3)
        self.assertTrue(trials[0]["passed"])
        self.assertFalse(trials[1]["passed"])
        self.assertTrue(trials[2]["passed"])

    def test_compute_measurement_preserves_matching_operations(self):
        responses = [
            (
                FakeResponse(200, headers={"X-Request-ID": "request-1"}),
                250.0,
            ),
            (
                FakeResponse(200, headers={"X-Request-ID": "request-2"}),
                350.0,
            ),
            (
                FakeResponse(200, {
                    "entries": [
                        {"request_id": "unrelated", "duration_ms": 999.0},
                        {"request_id": "request-1", "duration_ms": 100.0},
                        {"request_id": "request-2", "duration_ms": 200.0},
                    ],
                }),
                5.0,
            ),
        ]

        with patch.object(run_capstone, "LOG_TOKEN", "review-secret"), patch.object(
            run_capstone, "request", side_effect=responses,
        ):
            measurement = run_capstone.compute_measurement(count=2)

        self.assertEqual(measurement["successful_trials"], 2)
        self.assertEqual(measurement["preserved_operation_count"], 2)
        self.assertEqual(measurement["average_service_seconds"], 0.15)
        self.assertEqual(measurement["average_client_seconds"], 0.3)
        self.assertEqual(measurement["hundred_runs_service_seconds"], 15.0)
        self.assertEqual(
            [entry["request_id"] for entry in measurement["operations"]],
            ["request-1", "request-2"],
        )


if __name__ == "__main__":
    unittest.main()
