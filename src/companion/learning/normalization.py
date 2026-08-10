import re

TERMINAL_PUNCTUATION = re.compile(r"[.!?。！？]+$")
WHITESPACE = re.compile(r"\s+")


def normalize_learning_text(value: str) -> str:
    normalized = WHITESPACE.sub(" ", value.strip()).casefold()
    return TERMINAL_PUNCTUATION.sub("", normalized).rstrip()


def merge_answers(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for answer in [*existing, *incoming]:
        clean = WHITESPACE.sub(" ", answer.strip())
        key = normalize_learning_text(clean)
        if key and key not in seen:
            seen.add(key)
            merged.append(clean)
    return merged
