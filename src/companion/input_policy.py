HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)

ENGLISH_INPUT_REDIRECT = (
    "Please try saying that in English. If you need help, use /help or /hint."
)
BLOCKED_INPUT_SOURCE = "language_policy"


def is_materially_han(text: str) -> bool:
    """Return whether free-form input is materially Han-dominant.

    A single Han character is always treated as incidental. For longer input,
    Han must account for at least 30% of Han and Latin letters.
    """
    han_count = sum(_is_han(character) for character in text)
    if han_count < 2:
        return False
    latin_count = sum(character.isascii() and character.isalpha() for character in text)
    return han_count * 10 >= (han_count + latin_count) * 3


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in HAN_RANGES)
