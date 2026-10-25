"""Record real HTTP calibration, appeals, and validation checks (no model mocks).

Start app.py first, then run: python run_demo.py
All calibration writing is AI-authored, irrespective of the returned guess.
"""

import argparse
from datetime import datetime, timezone
import json

import requests

import config
from scenarios import CALIBRATION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=f"http://{config.HOST}:{config.PORT}")
    args = parser.parse_args()
    requests.get(f"{args.url}/health", timeout=10).raise_for_status()
    records = []
    verdicts = []

    def send(path, *, expected=200, **kwargs):
        response = requests.post(f"{args.url}{path}", timeout=300, **kwargs)
        body = response.json()
        records.append({
            "route": path,
            "request": kwargs.get("json", kwargs.get("data")),
            "content_type": kwargs.get("headers", {}).get("Content-Type", "application/json"),
            "status": response.status_code,
            "response": body,
        })
        if response.status_code != expected:
            raise RuntimeError(f"{path}: expected {expected}, got {response.status_code}: {body}")
        return body

    for trial in range(1, 4):
        baseline = requests.get(f"{args.url}/log", timeout=10)
        baseline.raise_for_status()
        baseline_count = baseline.json()["count"]
        outputs = []
        for index, case in enumerate(CALIBRATION):
            result = send("/submit", json={
                "text": case["text"], "creator_id": f"demo_t{trial}_case{index}",
            })
            outputs.append(result)
            print(
                f"Trial {trial} | {case['name']}: {result['guess']} | "
                f"model={result['model_score']} style={result['style_score']} "
                f"combined={result['combined_score']}"
            )

        content_id = outputs[0]["content_id"]
        history = requests.get(f"{args.url}/log", timeout=10)
        history.raise_for_status()
        original = next(e for e in history.json()["entries"] if e.get("content_id") == content_id)
        reasoning = "This is an AI-authored demonstration. Please review the recorded decision."
        appeal = send("/appeal", json={"content_id": content_id, "reasoning": reasoning})
        send("/appeal", expected=404, json={"content_id": "unknown-demo-id", "reasoning": reasoning})
        invalid = [
            ({}, 400),
            ({"text": "", "creator_id": "demo"}, 400),
            ({"text": "   ", "creator_id": "demo"}, 400),
            ({"text": None, "creator_id": "demo"}, 400),
            ({"text": 123, "creator_id": "demo"}, 400),
            ({"text": "three valid words"}, 400),
            ([], 400),
            ({"text": "hi", "creator_id": "demo"}, 422),
        ]
        for payload, status in invalid:
            send("/submit", expected=status, json=payload)
        send("/submit", expected=400, data="{", headers={"Content-Type": "application/json"})
        send("/submit", expected=415, data="not JSON", headers={"Content-Type": "text/plain"})
        send("/submit", expected=413, json={"text": "word " * 2001, "creator_id": "demo"})
        send("/submit", expected=413, data="x" * 65537, headers={"Content-Type": "application/json"})
        send("/appeal", expected=400, json={"content_id": content_id, "reasoning": "x" * 2001})
        log_response = requests.get(f"{args.url}/log", timeout=10)
        log_response.raise_for_status()
        new_entries = log_response.json()["entries"][baseline_count:]
        entries = [e for e in new_entries if e.get("content_id") == content_id]
        input_reasons = {
            "invalid_text", "invalid_creator_id", "invalid_json",
            "text_too_short", "unsupported_media_type",
        }
        input_rejections = [e for e in new_entries if e.get("reason") in input_reasons]
        size_rejections = [
            e for e in new_entries
            if e.get("reason") in {"text_too_long", "request_too_large", "invalid_reasoning"}
        ]
        verdicts.append({
            "trial": trial,
            "score_spread": round(outputs[0]["combined_score"] - outputs[1]["combined_score"], 4),
            "criterion_1": outputs[0]["combined_score"] - outputs[1]["combined_score"] >= 0.30,
            "criterion_2": (
                {r["guess"] for r in outputs} == {"human", "unsure", "ai"}
                and all(
                    isinstance(r[field], (int, float)) and 0 <= r[field] <= 1
                    for r in outputs
                    for field in ("model_score", "style_score", "combined_score", "confidence")
                )
            ),
            "criterion_3": (
                appeal["status"] == "under_review" and len(entries) == 2
                and entries[0] == original and entries[-1]["status"] == "under_review"
                and entries[-1]["creator_id"] == original["creator_id"]
                and entries[-1]["reasoning"] == reasoning
                and not any(
                    e.get("event") == "appeal" and e.get("content_id") == "unknown-demo-id"
                    for e in new_entries
                )
            ),
            "criterion_4": (
                len(input_rejections) == 10
                and all(e["status"] == "rejected" for e in input_rejections)
                and sum(e.get("status") == "decided" for e in new_entries) == 4
            ),
            "criterion_5": (
                len(size_rejections) == 3
                and all(e["status"] == "rejected" for e in size_rejections)
                and sum(e.get("event") == "appeal" for e in new_entries) == 1
            ),
        })
    config.RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = config.RESULTS_DIR / f"local_demo_{stamp}.json"
    path.write_text(json.dumps({
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "note": "Real local GPT-2 inference. All calibration passages are AI-authored.",
        "calibration": CALIBRATION,
        "trials": verdicts,
        "records": records,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdicts, indent=2))
    print(f"Recorded {path}")


if __name__ == "__main__":
    main()
