#!/usr/bin/env python3
"""Run the five committed capstone criteria against a hosted instance."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import requests


BASE_URL = os.environ.get("CAPSTONE_BASE_URL", "").rstrip("/")
LOG_TOKEN = os.environ.get("CAPSTONE_LOG_TOKEN", "")
TIMEOUT_SECONDS = float(os.environ.get("CAPSTONE_TIMEOUT_SECONDS", "240"))
RESULTS_DIR = Path(__file__).parent / "results"


def request(method: str, route: str, **kwargs) -> tuple[requests.Response, float]:
    started = perf_counter()
    response = requests.request(
        method,
        f"{BASE_URL}{route}",
        timeout=TIMEOUT_SECONDS,
        **kwargs,
    )
    return response, round((perf_counter() - started) * 1000, 3)


def health_trial() -> dict:
    response, duration_ms = request("GET", "/health")
    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError:
        body = None
    passed = response.status_code == 200 and isinstance(body, dict) and body.get("ok") is True
    return {
        "passed": passed,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "ok": body.get("ok") if isinstance(body, dict) else None,
    }


def unauthorized_trial(route: str) -> dict:
    response, duration_ms = request("GET", route)
    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError:
        body = None
    passed = response.status_code in (401, 403) and not (
        isinstance(body, dict) and ("entries" in body or "count" in body)
    )
    return {
        "passed": passed,
        "route": route,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "protected_data_returned": isinstance(body, dict) and (
            "entries" in body or "count" in body
        ),
    }


def method_error_trial() -> dict:
    response, duration_ms = request("POST", "/health")
    body = response.text
    lowered = body.lower()
    passed = (
        response.status_code == 405
        and "method not allowed" in lowered
        and "traceback" not in lowered
    )
    return {
        "passed": passed,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "contains_method_not_allowed": "method not allowed" in lowered,
        "contains_traceback": "traceback" in lowered,
    }


def sensitive_data_trials() -> list[dict]:
    dummy_values = [
        "dummy-password-capstone-1",
        "dummy-api-key-capstone-2",
        "dummy-auth-token-capstone-3",
    ]
    fields = ("password", "api_key", "auth_token")
    trials = []
    headers = {"Authorization": f"Bearer {LOG_TOKEN}"}

    for index, (field, value) in enumerate(zip(fields, dummy_values), start=1):
        response, duration_ms = request("POST", "/submit", json={
            "text": (
                "This synthetic capstone passage contains enough words for "
                "the hosted detector to evaluate without using private writing."
            ),
            "creator_id": f"capstone-sensitive-{index}",
            field: value,
        })
        log_response, _ = request("GET", "/log?limit=100", headers=headers)
        operations_response, _ = request("GET", "/operations?limit=100", headers=headers)
        inspected = log_response.text + operations_response.text
        leaked = [
            secret for secret in (value, LOG_TOKEN)
            if secret and secret in inspected
        ]
        trials.append({
            "passed": (
                response.status_code == 200
                and log_response.status_code == 200
                and operations_response.status_code == 200
                and not leaked
            ),
            "trial": index,
            "submission_status_code": response.status_code,
            "log_status_code": log_response.status_code,
            "operations_status_code": operations_response.status_code,
            "duration_ms": duration_ms,
            "unredacted_sensitive_value_count": len(leaked),
        })

    return trials


def criterion(name: str, trials: list[dict]) -> dict:
    return {
        "name": name,
        "verdict": "MET" if all(trial["passed"] for trial in trials) else "MISSED",
        "trials": trials,
    }


def render_markdown(run: dict) -> str:
    lines = [
        f"# Capstone hosted run — {run['timestamp']}",
        "",
        f"- Base URL: `{run['base_url']}`",
        f"- Overall verdict: **{run['verdict']}**",
        "",
    ]
    for number, result in enumerate(run["criteria"], start=1):
        lines.extend([
            f"## Criterion {number}: {result['name']}",
            "",
            f"**Verdict: {result['verdict']}**",
            "",
            "```json",
            json.dumps(result["trials"], indent=2, sort_keys=True),
            "```",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    if not BASE_URL:
        raise SystemExit("Set CAPSTONE_BASE_URL to the deployed service URL.")
    if not LOG_TOKEN:
        raise SystemExit("Set CAPSTONE_LOG_TOKEN to the hosted log-access token.")

    # Run latency first so its first trial includes the host's initial request.
    latency_trials = [health_trial() for _ in range(3)]
    availability_trials = [health_trial() for _ in range(3)]
    protection_trials = [
        unauthorized_trial(route)
        for route in ("/log", "/operations")
        for _ in range(3)
    ]
    error_trials = [method_error_trial() for _ in range(3)]
    sensitive_trials = sensitive_data_trials()

    results = [
        criterion("Hosted Service Availability", availability_trials),
        criterion("Protection of Logs and Operations", protection_trials),
        criterion("Latency", [
            {
                **trial,
                "passed": trial["passed"] and trial["duration_ms"] <= 1000,
            }
            for trial in latency_trials
        ]),
        criterion("Error Handling", error_trials),
        criterion("Sensitive Data Exclusion", sensitive_trials),
    ]
    run = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": BASE_URL,
        "verdict": "MET" if all(item["verdict"] == "MET" for item in results) else "MISSED",
        "criteria": results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output = RESULTS_DIR / f"capstone_hosted_{timestamp}.md"
    output.write_text(render_markdown(run), encoding="utf-8")
    print(output)
    print(f"Overall verdict: {run['verdict']}")
    return 0 if run["verdict"] == "MET" else 1


if __name__ == "__main__":
    raise SystemExit(main())
