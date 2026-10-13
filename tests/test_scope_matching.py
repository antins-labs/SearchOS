import pytest

from searchos.util.scope import match_entities_in_task


@pytest.mark.parametrize(
    ("task", "entities", "expected"),
    [
        ("APOLLO 7 与北京大学", ["Apollo 7", "北京大学", "清华大学"], {"Apollo 7", "北京大学"}),
        (
            "2019 winners",
            ["2019|James Peebles", "2019|Michel Mayor", "2020|Roger Penrose"],
            {"2019|James Peebles", "2019|Michel Mayor"},
        ),
        ("Tesla data", [" Tesla |2024", "Ford|2024"], {" Tesla |2024"}),
        ("A 1", ["A|1"], set()),
        ("A|1", ["A|1"], {"A|1"}),
        ("Apollo 11", ["Apollo 1", "Apollo 11"], {"Apollo 1", "Apollo 11"}),
        ("Apollo 7-17", ["Apollo 7", "Apollo 8", "Apollo 17"], {"Apollo 7"}),
        ("", ["Apollo 7"], set()),
        ("Apollo 7", [], set()),
    ],
)
def test_scope_matching_rules(task, entities, expected):
    assert match_entities_in_task(task, entities) == expected
