"""AI-authored calibration cases, not a human/AI accuracy dataset."""

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

SCENARIOS = [
    {"name": "score spread", "criterion": 1, "texts": [case["text"] for case in CALIBRATION[:2]]},
    {"name": "label coverage", "criterion": 2, "texts": [case["text"] for case in CALIBRATION]},
    {
        "name": "bad input", "criterion": 4,
        "bodies": [
            {"creator_id": "eval_missing"},
            {"text": "", "creator_id": "eval_empty"},
            {"text": "   ", "creator_id": "eval_blank"},
            {"text": None, "creator_id": "eval_null"},
            {"text": 123, "creator_id": "eval_number"},
            {"text": "three valid words"},
            {"text": "hi", "creator_id": "eval_short"},
        ],
    },
    {
        "name": "oversized text", "criterion": 5,
        "bodies": [{"text": "word " * 2001, "creator_id": "eval_huge"}],
    },
]


def validate() -> list[str]:
    problems = []
    for index, scenario in enumerate(SCENARIOS, 1):
        if not scenario.get("name"):
            problems.append(f"scenario {index} has no name")
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
