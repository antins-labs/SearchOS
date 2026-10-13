"""评测 reformat 的事实边界回归测试。"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import pandas as pd

from eval import reformat
from eval.reformat import core


class ReformatGroundingTests(unittest.TestCase):
    def test_semantically_empty_table_skips_reformat_model(self) -> None:
        raw = """\
| 届数 | 奖项名称 | 获奖歌曲/专辑 | 演唱者 |
|---|---|---|---|
| 第46届 |  |  |  |
"""

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("语义空表不应调用 reformat 模型")

        with patch.object(reformat, "reformat_widesearch", fail_if_called):
            result = asyncio.run(reformat.reformat_for_eval(
                raw,
                target="widesearch",
                original_query="列出获奖记录",
                required_columns=["届数", "奖项名称", "获奖歌曲/专辑", "演唱者"],
                key_columns=["届数", "奖项名称"],
            ))

        self.assertEqual(result, (None, None))

    def test_single_table_reformat_rejects_row_expansion(self) -> None:
        raw = """\
| 届数 | 奖项名称 | 获奖歌曲/专辑 | 演唱者 |
|---|---|---|---|
| 第46届 | Best Rap Album | Speakerboxxx/The Love Below | OutKast |
"""
        fabricated = """\
```markdown
| 届数 | 奖项名称 | 获奖歌曲/专辑 | 演唱者 |
|---|---|---|---|
| 第46届 | Best Rap Album | Speakerboxxx/The Love Below | OutKast |
| 第47届 | Best Rap Album | Fabricated Album | Fabricated Artist |
```
"""

        async def fake_model(*args, **kwargs):
            return fabricated

        with patch.object(core, "invoke_reformat_model", fake_model):
            block, frame = asyncio.run(core.join_and_reformat_with_llm(
                raw,
                target="widesearch",
                original_query="列出获奖记录",
                required_columns=["届数", "奖项名称", "获奖歌曲/专辑", "演唱者"],
                max_retries=1,
            ))

        self.assertIsNotNone(block)
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(len(frame), 1)
        self.assertNotIn("Fabricated Album", block or "")

    def test_code_join_declines_one_to_many_lookup(self) -> None:
        parent = pd.DataFrame([
            {"届数": "第46届", "年份": "2004"},
        ])
        children = pd.DataFrame([
            {"届数": "第46届", "奖项名称": "Best Rap Album"},
            {"届数": "第46届", "奖项名称": "Best Rap Song"},
        ])
        plan = {
            "base_table": 1,
            "joins": [{
                "lookup_table": 2,
                "on": [["届数", "届数"]],
                "bring": [["奖项名称", "奖项名称"]],
            }],
        }

        merged = core._execute_join_plan([parent, children], plan)

        self.assertIsNone(merged)

    def test_unresolved_multi_table_join_may_expand_beyond_input_sum(self) -> None:
        raw = """\
| Category | Author |
|---|---|
| C | A1 |
| C | A2 |

| Category | Book |
|---|---|
| C | B1 |
| C | B2 |
| C | B3 |
"""
        expanded = """\
```markdown
| Author | Book |
|---|---|
| A1 | B1 |
| A1 | B2 |
| A1 | B3 |
| A2 | B1 |
| A2 | B2 |
| A2 | B3 |
```
"""
        responses = iter([
            '{"needs_join": false}',
            expanded,
        ])

        async def fake_model(*args, **kwargs):
            return next(responses)

        with patch.object(core, "invoke_reformat_model", fake_model):
            block, frame = asyncio.run(core.join_and_reformat_with_llm(
                raw,
                target="widesearch",
                original_query="列出每位作者与每本书的组合",
                required_columns=["Author", "Book"],
                max_retries=1,
            ))

        self.assertIsNotNone(block)
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(len(frame), 6)


if __name__ == "__main__":
    unittest.main()
