import pytest

from companion.input_policy import is_materially_han


@pytest.mark.parametrize("text", ["我今天很累。", "你好 Andy", "這是一個 Chinese"])
def test_material_han_input_is_detected(text: str) -> None:
    assert is_materially_han(text)


@pytest.mark.parametrize(
    "text",
    ["I had a difficult day.", "Lesson 第 3 is useful.", "Visit https://example.com/中文"],
)
def test_english_and_incidental_han_are_allowed(text: str) -> None:
    assert not is_materially_han(text)
