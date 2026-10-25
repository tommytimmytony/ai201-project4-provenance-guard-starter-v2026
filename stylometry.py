"""Surface-pattern heuristics, not proof of authorship. Higher scores are AI-like."""

import re
import statistics
import string


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part for part in parts if part.strip()]


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def sentence_length_spread(text: str) -> float:
    """Sample standard deviation / mean word count; zero with <2 sentences."""
    lengths = [len(words(sentence)) for sentence in sentences(text)]
    lengths = [length for length in lengths if length]
    if len(lengths) < 2:
        return 0.0
    return statistics.stdev(lengths) / statistics.mean(lengths)


def type_token_ratio(text: str) -> float:
    """Unique lowercase words / total words; zero with no words."""
    tokens = words(text)
    return len(set(tokens)) / len(tokens) if tokens else 0.0


def punctuation_density(text: str) -> float:
    """ASCII punctuation characters / non-whitespace characters."""
    characters = [character for character in text if not character.isspace()]
    if not characters:
        return 0.0
    return sum(character in string.punctuation for character in characters) / len(characters)


def style_signal(text: str) -> float:
    """Combine normalized regularity, repetition, and sparse punctuation.

    Fewer than 20 words or two sentences gives 0.5 (insufficient evidence).
    Style assumptions are illustrative, English-oriented, and uncalibrated.
    """
    if len(words(text)) < 20 or len(sentences(text)) < 2:
        return 0.5
    regularity = 1.0 - min(sentence_length_spread(text), 1.0)
    repetition = 1.0 - type_token_ratio(text)
    sparse_punctuation = 1.0 - min(punctuation_density(text) / 0.1, 1.0)
    return round(0.5 * regularity + 0.3 * repetition + 0.2 * sparse_punctuation, 4)


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or (
        "The system works well. It handles most cases correctly and provides "
        "good results. Users generally find it easy to use and understand."
    )
    print(f"{len(sentences(text))} sentences, {len(words(text))} words\n")
    print(f"sentence_length_spread   {sentence_length_spread(text):.4f}")
    print(f"type_token_ratio         {type_token_ratio(text):.4f}")
    print(f"punctuation_density      {punctuation_density(text):.4f}")
    print(f"style_signal            {style_signal(text):.4f} (higher = more AI-like)")
