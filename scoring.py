"""Combine heuristic signals and map scores to non-accusatory reader labels."""

import math

import config

HUMAN_LABEL = (
    "This writing looks more like human writing to our checks. "
    "This is an estimate, not proof of who wrote it."
)
UNSURE_LABEL = (
    "Our checks cannot reliably tell how this was written. "
    "This is not an accusation; you can request a review."
)
AI_LABEL = (
    "Our checks found patterns that can appear in AI-generated writing. "
    "People can write this way too; you can request a review."
)


def _validate_score(score: float) -> None:
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("Scores must be finite numbers between 0 and 1.")


def combine_signals(model_score: float, style_score: float) -> float:
    """Equal-weight average; strong disagreement explicitly produces unsure."""
    _validate_score(model_score)
    _validate_score(style_score)
    if abs(model_score - style_score) >= config.DISAGREEMENT_THRESHOLD:
        return 0.5
    return round(
        config.WEIGHT_MODEL_SIGNAL * model_score
        + config.WEIGHT_STYLE_SIGNAL * style_score,
        4,
    )


def score_to_label(score: float) -> tuple[str, str]:
    _validate_score(score)
    if score >= config.AI_THRESHOLD:
        return "ai", AI_LABEL
    if score <= config.HUMAN_THRESHOLD:
        return "human", HUMAN_LABEL
    return "unsure", UNSURE_LABEL


def label_ranges() -> list[tuple[str, str]]:
    return [
        ("high-confidence human", f"0 <= score <= {config.HUMAN_THRESHOLD:.2f}"),
        ("unsure", f"{config.HUMAN_THRESHOLD:.2f} < score < {config.AI_THRESHOLD:.2f}"),
        ("high-confidence AI", f"{config.AI_THRESHOLD:.2f} <= score <= 1"),
    ]
