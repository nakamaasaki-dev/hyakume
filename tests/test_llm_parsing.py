import pytest

from hyakume.collect import _parse_items
from hyakume.llm import extract_json


def test_extract_json_from_fence():
    text = "結果です。\n```json\n[{\"a\": 1}]\n```\nおわり"
    assert extract_json(text) == [{"a": 1}]


def test_extract_json_without_fence():
    assert extract_json("prefix {\"x\": [1, 2]} suffix") == {"x": [1, 2]}


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_parse_items_clamps_interest_and_skips_invalid():
    text = """```json
    [{"title": "t", "url": "https://a/b", "summary": "s", "interest": 9},
     {"title": "bad"}]
    ```"""
    items = _parse_items(text)
    assert len(items) == 1
    assert items[0].interest == 5
    assert items[0].source == "web"
