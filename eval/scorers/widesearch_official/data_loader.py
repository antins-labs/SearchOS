"""Vendored WideSearch data loader (local-files only; HF/loguru deps removed).

Source: ``datasets/widesearch/WideSearch/src/evaluation/data_loader.py``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from io import StringIO
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def norm_column(col: str) -> str:
    return col.strip().lower().replace(" ", "")


@dataclass
class WideSearchQuery:
    instance_id: str
    query: str
    evaluation: dict
    answer: pd.DataFrame
    language: str


class WideSearchDataLoader:
    def __init__(self, data_path: str, answer_root: str):
        self.data = self._load(data_path, answer_root)

    @staticmethod
    def _load_answer(answer_path: str, required_columns) -> Optional[pd.DataFrame]:
        if not os.path.exists(answer_path):
            logger.error("answer_path %s not found", answer_path)
            return None
        answer = pd.read_csv(answer_path)
        answer.columns = [norm_column(c.strip()) for c in answer.columns]
        for col in required_columns:
            if col not in answer.columns:
                logger.error("required col %s missing in %s", col, answer_path)
                return None
        return answer[list(required_columns)]

    def _load(self, data_path: str, answer_root: str):
        if not os.path.exists(data_path):
            raise FileNotFoundError(data_path)
        records = pd.read_json(data_path, lines=True).to_dict(orient="records")
        out = {}
        for item in records:
            ev = item["evaluation"]
            if isinstance(ev, str):
                ev = json.loads(ev)
                item["evaluation"] = ev
            answer_path = f"{answer_root}/{item['instance_id']}.csv"
            answer = self._load_answer(answer_path, ev["required"])
            if answer is None:
                continue
            item["answer"] = answer
            out[item["instance_id"]] = WideSearchQuery(**item)
        logger.info("loaded %d queries from %s", len(out), data_path)
        return out

    def load_query_by_instance_id(self, instance_id: str) -> WideSearchQuery:
        assert instance_id in self.data, f"instance_id {instance_id} not found"
        return self.data[instance_id]

    def get_instance_id_list(self):
        return list(self.data.keys())


@dataclass
class WideSearchResponse:
    instance_id: str
    response: str
    messages: Optional[list] = None
    trial_idx: Optional[int] = None

    def extract_dataframe(self) -> Optional[pd.DataFrame]:
        markdown_str = re.findall(r"```markdown(.*?)```", self.response, re.DOTALL)
        if not markdown_str:
            pipe_positions = [m.start() for m in re.finditer(r"\|", self.response)]
            if len(pipe_positions) >= 4:
                first_pipe = pipe_positions[0]
                last_pipe = pipe_positions[-1]
                start = self.response.rfind("\n", 0, first_pipe)
                start = 0 if start == -1 else start
                end = self.response.find("\n", last_pipe)
                end = len(self.response) if end == -1 else end
                table_candidate = self.response[start:end]
                markdown_str = re.findall(r"((?:\|.*\n?)+)", table_candidate)
        if not markdown_str:
            logger.warning("no markdown table found in response %s", self.instance_id)
            return None

        text = markdown_str[0].strip()
        lines = text.split("\n")
        lines[0] = lines[0].replace(" ", "").lower()
        lines = [ln.strip() for ln in lines]
        new_lines = []
        for ln in lines:
            if set(ln.strip()).issubset(set("|- :")) or "|" not in ln:
                continue
            new_lines.append(ln)
        if not new_lines:
            logger.warning("no table rows in response %s", self.instance_id)
            return None

        # Parse the markdown table by hand instead of pd.read_csv(sep="|"):
        # a data cell holding an unescaped "|" yields more fields than the
        # header and makes the C parser raise, zeroing the whole question.
        def _cells(line: str) -> list[str]:
            s = line.strip()
            if s.startswith("|"):
                s = s[1:]
            if s.endswith("|"):
                s = s[:-1]
            return [p.strip() for p in s.split("|")]

        header = _cells(new_lines[0])
        ncol = len(header)
        rows = []
        for ln in new_lines[1:]:
            parts = _cells(ln)
            if len(parts) > ncol:
                # an intra-cell "|" over-split this row; fold the surplus
                # back into the last column rather than dropping the row.
                parts = parts[: ncol - 1] + ["|".join(parts[ncol - 1:])]
            elif len(parts) < ncol:
                parts = parts + [""] * (ncol - len(parts))
            rows.append(parts)
        df = pd.DataFrame(rows, columns=header)
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
        return df
