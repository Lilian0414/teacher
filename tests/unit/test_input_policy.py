from companion.input_policy import is_materially_chinese


def test_material_chinese_requires_more_than_incidental_han_text() -> None:
    assert is_materially_chinese("我今天真的很累。") is True
    assert is_materially_chinese("I visited 中文 class today at https://example.com.") is False
    assert is_materially_chinese("My friend 王 is here.") is False
    assert is_materially_chinese("I had a difficult day at school.") is False
