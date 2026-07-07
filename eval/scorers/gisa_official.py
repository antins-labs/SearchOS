"""Vendored GISA SimpleEvaluator.

Slimmed copy of ``datasets/GISA/GISA-main/eval_script/run_evaluation.py``.
Default scoring matches official GISA (strict, no LLM). Pass
``use_llm_judge=True`` (or set env ``GISA_LLM_JUDGE=1``) to enable
WideSearch-style semantic row alignment + per-cell judging.
"""

from __future__ import annotations

import difflib
import os
import re
import unicodedata
from collections import Counter
from io import StringIO
from typing import Optional, Tuple, Union

import numpy as np
import pandas as pd


# Surface-form variants folded symmetrically on pred and gold.
_UNICODE_FOLD = {
    "×": "x", "✕": "x", "✖": "x", "✗": "x",
    "–": "-", "—": "-", "−": "-",
    " ": " ", "　": " ",
    "％": "%",
    "‘": "'", "’": "'", "“": '"', "”": '"',
}


def _fold_unicode(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(_UNICODE_FOLD.get(c, c) for c in s)


_COL_SEP_RE = re.compile(r"[\s_\-]+")


def _norm_col(c) -> str:
    return _COL_SEP_RE.sub("", _fold_unicode(str(c)).strip().lower())


class SimpleEvaluator:
    _JUDGE_CRITERION = (
        "You are comparing a response value against a reference value for the "
        "same table column. Score 1 if they denote the SAME fact — allowing "
        "differences only in surface form: formatting, units, thousands "
        "separators, leading zeros, abbreviation vs full name, or the ordering "
        "of items inside a multi-value cell. Score 0 if the underlying value, "
        "quantity, date, or entity is genuinely different."
    )

    _ITEM_CRITERION = (
        "The reference is the single correct answer to a question (a number, "
        "name, date, or entity). The response is a model's final answer, which "
        "may include explanation around the answer. Score 1 if the response "
        "clearly states an answer that denotes the SAME fact as the reference, "
        "allowing surface-form differences (formatting, units, thousands "
        "separators, abbreviation vs full name, extra wording). Score 0 if the "
        "stated answer is a genuinely different value/entity, or the response "
        "states no answer / 'not found' / is empty."
    )

    def __init__(self, use_llm_judge: bool = False):
        self.use_llm_judge = use_llm_judge or os.environ.get("GISA_LLM_JUDGE") == "1"

    def _normalize_val(self, val: Union[str, int, float]) -> str:
        val_str = _fold_unicode(str(val)).strip()
        if not val_str or val_str.lower() in ["nan", "none", "null"]:
            return ""

        clean_num = val_str.replace(",", "").replace("$", "")
        is_percent = False
        if clean_num.endswith("%"):
            is_percent = True
            clean_num = clean_num[:-1]

        try:
            f_val = float(clean_num)
            if is_percent:
                f_val /= 100.0
            if f_val.is_integer():
                return str(int(f_val))
            formatted = "{:.6f}".format(f_val).rstrip("0").rstrip(".")
            return formatted if formatted else "0"
        except ValueError:
            pass

        return val_str.lower().replace(" ", "").replace("*", "").replace("\n", "")

    def _extract_model_output(self, model_output: str) -> Optional[pd.DataFrame]:
        pattern = r"```(?:tsv)?\s*(.*?)```"
        match = re.search(pattern, model_output, re.DOTALL)
        raw_content = match.group(1) if match else model_output
        try:
            raw_content = "\n".join([ln for ln in raw_content.split("\n") if ln.strip()])
            if not raw_content:
                return None
            output = pd.read_csv(StringIO(raw_content), sep="\t")
            output.columns = [_norm_col(c) for c in output.columns]
            output = output.map(self._normalize_val)
            return output
        except Exception:
            return None

    def load_ground_truth(self, file_path: str, question_type: str = "table") -> pd.DataFrame:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"GT file not found: {file_path}")
        header = "infer" if question_type == "table" else None
        try:
            df = pd.read_csv(file_path, header=header)
        except Exception as e:
            if "codec" in str(e):
                df = pd.read_csv(file_path, header=header, encoding="gbk")
            else:
                raise
        df.columns = [_norm_col(c) for c in df.columns]
        df = df.map(self._normalize_val)
        return df

    @staticmethod
    def _f1(tp: int, n_pred: int, n_gt: int) -> Tuple[float, float, float]:
        p = tp / n_pred if n_pred > 0 else 0.0
        r = tp / n_gt if n_gt > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return p, r, f1

    @staticmethod
    def _flatten(df: pd.DataFrame):
        items = []
        for col in df.columns:
            for val in df[col]:
                items.append((col, val))
        return items

    def evaluate_item(self, prediction, gt_df, gt_path: Optional[str] = None) -> dict:
        """Single-fact answer. Strict normalized exact match by default; LLM
        judge (when enabled) reads the answer out of possibly-verbose prose."""
        gt_item = ""
        if gt_path and os.path.exists(gt_path):
            try:
                gt_item = open(gt_path, encoding="utf-8", errors="ignore").read()
                gt_item = gt_item.lstrip("﻿").strip().strip('"')
            except Exception:
                gt_item = ""
        if not gt_item and not gt_df.empty:
            gt_item = ", ".join(str(x) for x in gt_df.iloc[0, :].tolist())

        pred_text = prediction or ""
        if isinstance(pred_text, str) and pred_text.endswith(".csv"):
            pdf = self.load_ground_truth(pred_text, question_type="item")
            pred_text = (
                ", ".join(str(x) for x in pdf.iloc[0, :].tolist())
                if pdf is not None and not pdf.empty else ""
            )
        if not str(pred_text).strip():
            return {"item_em": 0}

        if self.use_llm_judge:
            try:
                from .widesearch_official.metric_utils import llm_judge_column
                scores, _ = llm_judge_column(
                    [str(pred_text)], [gt_item], self._ITEM_CRITERION, "default_eval_config"
                )
                if scores and scores[0] is not None:
                    return {"item_em": int(scores[0])}
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "GISA item llm-judge failed (%s); falling back to exact match.", e
                )

        pred_df = self._extract_model_output(str(pred_text))
        pred_norm = (
            "".join(pred_df.iloc[0, :].tolist()) if pred_df is not None and not pred_df.empty
            else self._normalize_val(pred_text)
        )
        gt_norm = (
            "".join(gt_df.iloc[0, :].tolist()) if not gt_df.empty
            else self._normalize_val(gt_item)
        )
        return {"item_em": int(pred_norm == gt_norm)}

    def evaluate_set(self, pred_df, gt_df) -> dict:
        if pred_df is None or pred_df.empty:
            return {"set_precision": 0.0, "set_recall": 0.0, "set_f1": 0.0}
        pred_set = set(pred_df.iloc[:, -1].tolist())
        gt_set = set(gt_df.iloc[:, -1].tolist())
        tp = len(pred_set & gt_set)
        p, r, f1 = self._f1(tp, len(pred_set), len(gt_set))
        return {"set_precision": p, "set_recall": r, "set_f1": f1}

    def evaluate_list(self, pred_df, gt_df) -> dict:
        if pred_df is None or pred_df.empty:
            return {"list_content_f1": 0.0, "list_order_score": 0.0}
        pred_list = pred_df.iloc[:, -1].tolist()
        gt_list = gt_df.iloc[:, -1].tolist()
        gt_c, pred_c = Counter(gt_list), Counter(pred_list)
        common = sum((gt_c & pred_c).values())
        precision = common / len(pred_list) if pred_list else 0.0
        recall = common / len(gt_list) if gt_list else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        order_score = difflib.SequenceMatcher(None, gt_list, pred_list).ratio()
        return {"list_content_f1": round(f1, 4), "list_order_score": round(order_score, 4)}

    def evaluate_table(self, pred_df, gt_df) -> dict:
        default = {
            "table_row_f1": 0.0, "table_row_precision": 0.0, "table_row_recall": 0.0,
            "table_item_f1": 0.0, "table_item_precision": 0.0, "table_item_recall": 0.0,
        }
        if pred_df is None or pred_df.empty:
            return default

        # Score over common columns only (official GISA), surfacing coverage.
        common_cols = [c for c in gt_df.columns if c in pred_df.columns]
        n_gold_cols = len(gt_df.columns)
        coverage = {
            "schema_coverage": round(len(common_cols) / n_gold_cols, 4) if n_gold_cols else 0.0,
            "pk_only_match": int(len(common_cols) == 1 and n_gold_cols > 1),
            "missing_cols": [str(c) for c in gt_df.columns if c not in pred_df.columns],
        }
        if self.use_llm_judge and common_cols:
            judged = self._evaluate_table_judged(pred_df, gt_df, common_cols)
            if judged is not None:
                return {**judged, **coverage}

        # Official strict path: exact full-row set intersection.
        if not common_cols:
            row_p, row_r, row_f1 = 0.0, 0.0, 0.0
        else:
            pred_rows = set(tuple(r) for r in pred_df[common_cols].fillna("__NAN__").astype(str).to_numpy())
            gt_rows = set(tuple(r) for r in gt_df[common_cols].fillna("__NAN__").astype(str).to_numpy())
            tp = len(pred_rows & gt_rows)
            row_p, row_r, row_f1 = self._f1(tp, len(pred_rows), len(gt_rows))

        pred_items = self._flatten(pred_df)
        gt_items = self._flatten(gt_df)
        pc, gc = Counter(pred_items), Counter(gt_items)
        tp_items = sum((pc & gc).values())
        item_p, item_r, item_f1 = self._f1(tp_items, sum(pc.values()), sum(gc.values()))

        return {
            "table_row_f1": row_f1, "table_row_precision": row_p, "table_row_recall": row_r,
            "table_item_f1": item_f1, "table_item_precision": item_p, "table_item_recall": item_r,
            **coverage,
        }

    @staticmethod
    def _identity_key(gold, common_cols) -> list:
        """Smallest leading prefix of ``common_cols`` that uniquely keys gold
        rows; falls back to all columns when no prefix is unique."""
        for k in range(1, len(common_cols) + 1):
            prefix = common_cols[:k]
            if not gold[prefix].duplicated().any():
                return prefix
        return list(common_cols)

    def _evaluate_table_judged(self, pred_df, gt_df, common_cols) -> Optional[dict]:
        """LLM-aligned row identity + per-column judge. Row score is the
        per-row min across columns; item score sums every cell. Returns None on
        any judge-infra failure so the caller falls back to strict matching."""
        try:
            from .widesearch_official.metric_utils import (
                llm_judge_column,
                primary_key_preprocess,
            )

            pred = pred_df[common_cols].copy().astype(str)
            gold = gt_df[common_cols].copy().astype(str)

            key_cols = self._identity_key(gold, common_cols)
            value_cols = [c for c in common_cols if c not in key_cols]

            if len(key_cols) == 1:
                pk = key_cols[0]
            else:
                _SEP = " ||| "
                pk = "__identity_pk__"
                gold[pk] = gold[key_cols].apply(lambda r: _SEP.join(r), axis=1)
                pred[pk] = pred[key_cols].apply(lambda r: _SEP.join(r), axis=1)

            pred.drop_duplicates(subset=[pk], inplace=True)
            gold.drop_duplicates(subset=[pk], inplace=True)

            pk_map = primary_key_preprocess(
                pred[pk].tolist(), gold[pk].tolist(), "default_eval_config"
            )
            if isinstance(pk_map, dict):
                pred[pk] = pred[pk].apply(lambda x: pk_map.get(x, x))

            # De-dup again: mapped keys may now collide and inflate tp.
            pred.drop_duplicates(subset=[pk], inplace=True)

            merged = gold.merge(pred, on=pk, how="inner", suffixes=("_gt", "_pred"))

            n_pred_rows = len(pred)
            n_gt_rows = len(gold)
            n_cols = len(common_cols)

            # Identity columns score 1.0 (matched via key); value columns judged.
            col_scores = {c: [1.0] * len(merged) for c in key_cols}
            for col in value_cols:
                resp = merged[f"{col}_pred"].tolist()
                tgt = merged[f"{col}_gt"].tolist()
                if not resp:
                    col_scores[col] = []
                    continue
                scores, _ = llm_judge_column(resp, tgt, self._JUDGE_CRITERION, "default_eval_config")
                col_scores[col] = [float(s) if s is not None else 0.0 for s in scores]

            score_cols = key_cols + value_cols
            tp_row = 0.0
            tp_item = 0.0
            for i in range(len(merged)):
                row_vals = [col_scores[c][i] for c in score_cols]
                tp_row += min(row_vals)
                tp_item += sum(row_vals)

            row_p, row_r, row_f1 = self._f1_float(tp_row, n_pred_rows, n_gt_rows)
            item_p, item_r, item_f1 = self._f1_float(
                tp_item, n_pred_rows * n_cols, n_gt_rows * n_cols
            )
            return {
                "table_row_f1": row_f1, "table_row_precision": row_p, "table_row_recall": row_r,
                "table_item_f1": item_f1, "table_item_precision": item_p, "table_item_recall": item_r,
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "GISA llm-judge table scoring failed (%s); falling back to strict match.", e
            )
            return None

    @staticmethod
    def _f1_float(tp: float, n_pred: int, n_gt: int) -> Tuple[float, float, float]:
        p = tp / n_pred if n_pred > 0 else 0.0
        r = tp / n_gt if n_gt > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 1e-9 else 0.0
        return p, r, f1

    def evaluate_one(self, prediction: str, gt_path: str, question_type: str, qid=None) -> dict:
        q_type = question_type.lower()
        gt_df = self.load_ground_truth(gt_path, question_type=q_type)

        if q_type == "item":
            metrics = self.evaluate_item(prediction, gt_df, gt_path)
            metrics["global_em"] = int(metrics.get("item_em", 0))
            metrics["question_type"] = question_type
            return metrics

        if isinstance(prediction, str) and prediction.endswith(".csv"):
            pred_df = self.load_ground_truth(prediction, question_type=q_type)
        else:
            pred_df = self._extract_model_output(prediction or "")

        if q_type == "set":
            metrics = self.evaluate_set(pred_df, gt_df)
        elif q_type == "list":
            metrics = self.evaluate_list(pred_df, gt_df)
        else:
            metrics = self.evaluate_table(pred_df, gt_df)

        if pred_df is not None:
            if q_type != "set":
                metrics["global_em"] = int(np.array_equal(pred_df.to_numpy(), gt_df.to_numpy()))
            else:
                metrics["global_em"] = int(
                    set(pred_df.iloc[:, 0].tolist()) == set(gt_df.iloc[:, 0].tolist())
                )
        else:
            metrics["global_em"] = 0
        metrics["question_type"] = question_type
        return metrics

    @staticmethod
    def gather_results(score_list):
        df = pd.DataFrame(score_list)
        if df.empty:
            return {}
        overall_em = float(df["global_em"].mean())
        type_report = df.groupby("question_type").mean(numeric_only=True).round(4)
        detail = type_report.to_dict(orient="index")
        count_by_type = df["question_type"].value_counts().to_dict()
        summary = {"overall_global_em": overall_em}
        if "pk_only_match" in df.columns:
            n_pk_only = int(pd.to_numeric(df["pk_only_match"], errors="coerce").fillna(0).sum())
            if n_pk_only:
                summary["n_pk_only_match"] = n_pk_only
        for t, n in count_by_type.items():
            summary[t] = {
                "num_samples": int(n),
                **{f"overall_{k}": round(v, 4) for k, v in detail[t].items() if not pd.isna(v)},
            }
        return summary
