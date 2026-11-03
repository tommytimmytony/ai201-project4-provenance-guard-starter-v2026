"""Execute the five unchanged reference criteria with real HTTP evidence.

Calibration is AI-authored, not a human/AI accuracy dataset.
"""

import json
import math

import requests

CALIBRATION = [
    {
        "name": "regular repetitive prose",
        "text": "The system provides reliable results for every user. " * 8,
        "provenance": "AI-authored synthetic repetitive prose",
    },
    {
        "name": "irregular narrative",
        "text": (
            "Stop! I lugged my dented kettle uphill, past briars, shouting: 'Why today?' "
            "Nobody answered; dusk bruised the ridge. Fine. "
            "We camped beside a crooked fence, counted twelve moths, and forgot the tea. "
            "My left boot squeaked. Somewhere below us, a tractor coughed twice; "
            "Mara insisted it sounded like her grandfather's accordion."
        ),
        "provenance": "AI-authored narrative imitation; NOT genuine human writing",
    },
    {
        "name": "formal explanation",
        "text": (
            "A review procedure should preserve the original decision and record subsequent "
            "objections separately. The resulting history allows a reviewer to distinguish "
            "an initial estimate from a later challenge. Such a record does not establish "
            "who wrote the underlying document; it establishes what the service did."
        ),
        "provenance": "AI-authored formal prose; NOT genuine human writing",
    },
    {
        "name": "edited conversational prose",
        "text": (
            "Okay, here's the plan. We'll try the tool on a few drafts, but don't treat "
            "its answer as a verdict. My neatest paragraph might look predictable. "
            "A generated paragraph with some odd wording might slip through instead. "
            "If that happens, keep the scores and ask for a review."
        ),
        "provenance": "AI-authored conversational prose, edited by AI",
    },
]

def send(url, route, timeout, records, **kwargs):
    response = requests.post(f"{url}{route}", timeout=timeout, **kwargs)
    payload = response.json()
    records.append({
        "route": route,
        "request": kwargs.get("json", kwargs.get("data")),
        "content_type": kwargs.get("headers", {}).get("Content-Type", "application/json"),
        "status": response.status_code,
        "response": payload,
    })
    return response.status_code, payload


def log_entries(url, timeout):
    response = requests.get(f"{url}/log", timeout=timeout)
    response.raise_for_status()
    return response.json()["entries"]


def calibration_outputs(url, trial, timeout, records, count, criterion):
    outputs = []
    for i, case in enumerate(CALIBRATION[:count]):
        outputs.append(send(url, "/submit", timeout, records, json={
            "text": case["text"], "creator_id": f"eval_c{criterion}_t{trial}_{i}",
        }))
    return outputs


def score_spread(url, trial, timeout):
    records = []
    outputs = calibration_outputs(url, trial, timeout, records, 2, 1)
    valid = all(status == 200 for status, _ in outputs)
    spread = (
        round(outputs[0][1]["combined_score"] - outputs[1][1]["combined_score"], 4)
        if valid else None
    )
    return {"measurement": spread, "met": valid and spread >= 0.30, "records": records}


def label_coverage(url, trial, timeout):
    records = []
    outputs = calibration_outputs(url, trial, timeout, records, 4, 2)
    guesses = {payload.get("guess") for status, payload in outputs if status == 200}
    bounded = all(
        status == 200 and all(
            isinstance(payload.get(field), (int, float))
            and not isinstance(payload[field], bool)
            and math.isfinite(payload[field]) and 0 <= payload[field] <= 1
            for field in ("model_score", "style_score", "combined_score", "confidence")
        )
        for status, payload in outputs
    )
    return {
        "measurement": f"{len(guesses & {'human', 'unsure', 'ai'})}/3",
        "met": guesses == {"human", "unsure", "ai"} and bounded,
        "records": records,
    }


def appeal_traceability(url, trial, timeout):
    records = []
    baseline = len(log_entries(url, timeout))
    status, submission = calibration_outputs(url, trial, timeout, records, 1, 3)[0]
    if status != 200:
        return {"measurement": "0/3", "met": False, "records": records}
    content_id = submission["content_id"]
    original = next(entry for entry in log_entries(url, timeout) if entry.get("content_id") == content_id)
    reasoning = "AI-authored evaluation case: please preserve and review the original decision."
    appeal_status, appeal = send(url, "/appeal", timeout, records, json={
        "content_id": content_id, "reasoning": reasoning,
    })
    unknown = f"unknown_eval_t{trial}"
    unknown_status, _ = send(url, "/appeal", timeout, records, json={
        "content_id": unknown, "reasoning": reasoning,
    })
    entries = log_entries(url, timeout)[baseline:]
    history = [entry for entry in entries if entry.get("content_id") == content_id]
    checks = [
        appeal_status == 200 and appeal.get("status") == "under_review",
        len(history) == 2 and history[0] == original
        and history[1].get("status") == "under_review"
        and history[1].get("creator_id") == original["creator_id"]
        and history[1].get("reasoning") == reasoning,
        unknown_status == 404 and not any(
            entry.get("content_id") == unknown and entry.get("event") == "appeal"
            for entry in entries
        ),
    ]
    return {
        "measurement": f"{sum(checks)}/3", "met": all(checks),
        "records": records, "audit_entries": entries,
    }


def rejection_check(url, timeout, records, cases):
    baseline = len(log_entries(url, timeout))
    checks = []
    for kwargs, expected in cases:
        status, payload = send(url, "/submit" if kwargs.get("route") is None else kwargs["route"],
                               timeout, records, **{k: v for k, v in kwargs.items() if k != "route"})
        checks.append(status == expected and "error" in payload)
    entries = log_entries(url, timeout)[baseline:]
    complete_log = len(entries) == len(cases) and all(
        entry.get("status") == "rejected" and entry.get("reason") for entry in entries
    )
    return {
        "measurement": f"{sum(checks)}/{len(checks)}",
        "met": all(checks) and complete_log,
        "records": records, "audit_entries": entries,
        "rejections_logged": complete_log,
    }


def invalid_input(url, trial, timeout):
    records = []
    creator = f"eval_invalid_t{trial}"
    bodies = [
        {"creator_id": creator},
        {"text": "", "creator_id": creator},
        {"text": "   ", "creator_id": creator},
        {"text": None, "creator_id": creator},
        {"text": 123, "creator_id": creator},
        {"text": "three valid words"},
        [], None, "not an object",
    ]
    cases = [({"data": json.dumps(body),
               "headers": {"Content-Type": "application/json"}}, 400) for body in bodies]
    cases.extend([
        ({"data": "{", "headers": {"Content-Type": "application/json"}}, 400),
        ({"data": "not JSON", "headers": {"Content-Type": "text/plain"}}, 415),
        ({"json": {"text": "hi", "creator_id": creator}}, 422),
    ])
    return rejection_check(url, timeout, records, cases)


def size_limits(url, trial, timeout):
    records = []
    return rejection_check(url, timeout, records, [
        ({"json": {"text": "word " * 2001, "creator_id": f"eval_huge_t{trial}"}}, 413),
        ({"data": "x" * 65537, "headers": {"Content-Type": "application/json"}}, 413),
        ({"route": "/appeal", "json": {"content_id": "unknown", "reasoning": "x" * 2001}}, 400),
    ])


SCENARIOS = [
    {"name": "score spread", "criterion": 1, "target": "spread >= 0.30", "run": score_spread},
    {"name": "label coverage", "criterion": 2, "target": "3/3 labels; all scores bounded", "run": label_coverage},
    {"name": "appeal traceability", "criterion": 3, "target": "3/3 traceability checks", "run": appeal_traceability},
    {
        "name": "invalid input", "criterion": 4, "target": "12/12 expected rejections; all logged",
        "run": invalid_input, "pause_before": 65, "pause_between_trials": 65,
    },
    {"name": "size limits", "criterion": 5, "target": "3/3 expected rejections; all logged", "run": size_limits},
]


def validate() -> list[str]:
    problems = []
    if {scenario.get("criterion") for scenario in SCENARIOS} != {1, 2, 3, 4, 5} or len(SCENARIOS) != 5:
        problems.append("provide exactly one scenario for each of the five unchanged criteria")
    for index, scenario in enumerate(SCENARIOS, 1):
        if not scenario.get("name"):
            problems.append(f"scenario {index} has no name")
        if callable(scenario.get("run")):
            if not scenario.get("target"):
                problems.append(f"scenario {index} has no target")
            continue
        texts = scenario.get("texts")
        bodies = scenario.get("bodies")
        if bool(texts) == bool(bodies):
            problems.append(f"scenario {index} must have either texts or bodies")
        elif bodies:
            if not all(isinstance(body, dict) for body in bodies):
                problems.append(f"scenario {index} contains a non-object body")
        elif not all(isinstance(text, str) and text.strip() for text in texts):
            problems.append(f"scenario {index} contains invalid text")
    return problems
