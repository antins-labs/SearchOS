"""eval_table 多表导出的数据保全回归测试。"""

import unittest

from searchos.harness.report.eval_table_export import build_eval_table
from searchos.socm import EvidenceNode, ForeignKey, Relation, SearchState


class EvalTableExportTests(unittest.TestCase):
    def test_does_not_drop_child_rows_when_foreign_key_surface_differs(self) -> None:
        state = SearchState(intent="test")
        cmap = state.coverage_map
        cmap.add_table(
            "格莱美届次",
            ["届数"],
            primary_key=["届数"],
            entities=["第46届"],
        )
        cmap.add_table(
            "说唱奖项获奖记录",
            ["届数", "奖项名称", "获奖歌曲/专辑", "演唱者"],
            primary_key=["届数", "奖项名称"],
            entities=["46|Best Rap Album"],
        )
        cmap.add_relation(Relation(
            from_table="说唱奖项获奖记录",
            foreign_key=ForeignKey(
                target_table="格莱美届次",
                columns=["届数"],
                target_columns=["届数"],
            ),
        ))
        nodes = [
            EvidenceNode(
                id="song",
                table_id="说唱奖项获奖记录",
                entity="46|Best Rap Album",
                attribute="获奖歌曲/专辑",
                value="Speakerboxxx/The Love Below",
                alignment="full",
            ),
            EvidenceNode(
                id="artist",
                table_id="说唱奖项获奖记录",
                entity="46|Best Rap Album",
                attribute="演唱者",
                value="OutKast",
                alignment="full",
            ),
        ]
        for node in nodes:
            state.evidence_graph.add_node(node)
        cmap.fill_from_evidence(nodes)

        exported = build_eval_table(state)

        self.assertIn("Speakerboxxx/The Love Below", exported)
        self.assertIn("OutKast", exported)
        self.assertEqual(
            exported.count("| 届数 | 奖项名称 | 获奖歌曲/专辑 | 演唱者 |"),
            1,
        )

    def test_non_redundant_parent_falls_back_without_losing_child_data(self) -> None:
        state = SearchState(intent="test")
        cmap = state.coverage_map
        cmap.add_table(
            "格莱美届次",
            ["届数", "年份"],
            primary_key=["届数"],
            entities=["第46届"],
        )
        cmap.add_table(
            "说唱奖项获奖记录",
            ["届数", "奖项名称", "获奖歌曲/专辑"],
            primary_key=["届数", "奖项名称"],
            entities=["46|Best Rap Album"],
        )
        cmap.add_relation(Relation(
            from_table="说唱奖项获奖记录",
            foreign_key=ForeignKey(
                target_table="格莱美届次",
                columns=["届数"],
                target_columns=["届数"],
            ),
        ))
        nodes = [
            EvidenceNode(
                id="year",
                table_id="格莱美届次",
                entity="第46届",
                attribute="年份",
                value="2004",
                alignment="full",
            ),
            EvidenceNode(
                id="song",
                table_id="说唱奖项获奖记录",
                entity="46|Best Rap Album",
                attribute="获奖歌曲/专辑",
                value="Speakerboxxx/The Love Below",
                alignment="full",
            ),
        ]
        for node in nodes:
            state.evidence_graph.add_node(node)
        cmap.fill_from_evidence(nodes)

        exported = build_eval_table(state)

        self.assertIn("2004", exported)
        self.assertIn("Speakerboxxx/The Love Below", exported)


if __name__ == "__main__":
    unittest.main()
