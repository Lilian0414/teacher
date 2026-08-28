ENGLISH_INPUT_REDIRECT = "Please try saying that in English. If you need help, use /help or /hint."


def is_materially_chinese(value: str) -> bool:
    """Return whether Han script materially outweighs Latin-script input."""
    han_count = sum(
        "\u3400" <= character <= "\u4dbf"
        or "\u4e00" <= character <= "\u9fff"
        or "\uf900" <= character <= "\ufaff"
        for character in value
    )
    latin_count = sum(character.isascii() and character.isalpha() for character in value)
    return han_count >= 2 and han_count >= latin_count
