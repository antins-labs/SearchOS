"""Vendored WideSearch ``evaluate_single_query`` (no pandarallel; sync apply)."""

from __future__ import annotations

import logging
import traceback
from copy import deepcopy
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .data_loader import WideSearchQuery, WideSearchResponse, norm_column
from .metric_utils import (
    llm_judge_column,
    metric_function_registry,
    norm_str,
    preprocess_function_registry,
    primary_key_preprocess,
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    instance_id: str
    score: float = 0.0
    precision_by_row: float = 0.0
    recall_by_row: float = 0.0
    f1_by_row: float = 0.0
    precision_by_item: float = 0.0
    recall_by_item: float = 0.0
    f1_by_item: float = 0.0
    # Aggregate per-column metrics (mean over all required columns).
    # Same shape as *_by_row / *_by_item — easy to compare side by side.
    precision_by_col: float = 0.0
    recall_by_col: float = 0.0
    f1_by_col: float = 0.0
    # Per-column breakdown — col name -> {precision_by_col, recall_by_col, f1_by_col, tp}.
    column_metrics: dict = None
    msg: str = ""


def _preprocess(content, name):
    return preprocess_function_registry[name](content)


def _metric(response, target, criterion, name):
    fn = metric_function_registry[name]
    if name in ("llm_judge", "number_near"):
        return fn(response, target, criterion)
    return fn(response, target)


def evaluate_single_query(
    query: WideSearchQuery,
    response: Optional[WideSearchResponse],
    result_save_path: Optional[str] = None,
    eval_model_config_name: str = "default_eval_config",
) -> EvaluationResult:
    if response is None:
        return EvaluationResult(instance_id=query.instance_id, msg="response is None")

    assert query.instance_id == response.instance_id

    score = 0.0
    precision_by_row = recall_by_row = f1_by_row = 0.0
    precision_by_item = recall_by_item = f1_by_item = 0.0
    msg = ""

    try:
        required_columns = query.evaluation["required"]
        unique_columns = query.evaluation["unique_columns"]
        answer_df = query.answer.copy()
        answer_df.columns = [norm_column(c) for c in answer_df.columns]

        response_df = response.extract_dataframe()
        if response_df is None:
            return EvaluationResult(instance_id=query.instance_id, msg="response_df is None")
        response_df.columns = [norm_column(c) for c in response_df.columns]

        if set(required_columns) != set(response_df.columns):
            column_map = primary_key_preprocess(
                response_df.columns.tolist(), required_columns, eval_model_config_name
            )
            response_df.rename(columns=column_map, inplace=True)

        if set(required_columns) != set(response_df.columns):
            return EvaluationResult(
                instance_id=query.instance_id,
                msg=f"required {required_columns} != response {list(response_df.columns)}",
            )

        for col in required_columns:
            try:
                a_t, r_t = answer_df[col].dtype, response_df[col].dtype
            except Exception:
                a_t = r_t = None
            if (r_t == float and a_t == int) or (r_t == int and a_t == float):
                if r_t == int:
                    response_df[col] = response_df[col].astype(float)
                else:
                    answer_df[col] = answer_df[col].astype(float)
            answer_df[col] = answer_df[col].astype(str)
            response_df[col] = response_df[col].astype(str)

        response_df.drop_duplicates(subset=unique_columns, inplace=True)
        answer_df.drop_duplicates(subset=unique_columns, inplace=True)

        # primary-key alignment for unique columns that need llm_judge / exact_match
        for col in unique_columns:
            item = query.evaluation["eval_pipeline"].get(col, None)
            if item is None:
                continue
            metric_list = item.get("metric", [])
            if "llm_judge" in metric_list or "exact_match" in metric_list:
                pk_map = primary_key_preprocess(
                    response_df[col].tolist(), answer_df[col].tolist(), eval_model_config_name,
                )
                response_df[col + "_before_map"] = response_df[col]
                # The LLM alignment map may only rescue values that do NOT
                # already match the gold column; applied unconditionally it
                # can rewrite an exact match onto a same-meaning gold variant
                # from a *different* row (ws_zh_008: golden's 专业组 wording
                # differs by year, and remapping 2024-style values onto the
                # 2020-style variant emptied the inner join entirely).
                gold_vals = {norm_str(v) for v in answer_df[col]}
                response_df[col] = response_df[col].apply(
                    lambda x: x if norm_str(x) in gold_vals else pk_map.get(x, x)
                )

        for col, item in query.evaluation["eval_pipeline"].items():
            for pname in item.get("preprocess", []):
                response_df[col] = response_df[col].apply(lambda x, p=pname: _preprocess(x, p))
                answer_df[col] = answer_df[col].apply(lambda x, p=pname: _preprocess(x, p))

        # global exact-match
        if answer_df.shape == response_df.shape:
            gt_s = answer_df.sort_values(by=required_columns).reset_index(drop=True)
            pr_s = response_df.sort_values(by=required_columns).reset_index(drop=True)
            if gt_s.equals(pr_s):
                score = 1.0

        df_inner = pd.merge(
            answer_df, response_df, on=unique_columns, how="inner",
            suffixes=("_query", "_response"),
        )

        a_outer = deepcopy(answer_df)
        a_outer["exist_flag_gt"] = 1
        r_outer = deepcopy(response_df)
        r_outer["exist_flag_response"] = 1
        df_outer = pd.merge(a_outer, r_outer, on=unique_columns, how="outer",
                            suffixes=("_query", "_response"))
        df_outer_wo_inner = df_outer[
            df_outer["exist_flag_gt"].isna() | df_outer["exist_flag_response"].isna()
        ]

        df_inner_score = pd.DataFrame(index=df_inner.index)
        df_inner_msg = pd.DataFrame(index=df_inner.index)

        # An empty inner join (zero primary-key matches) must score 0, not
        # crash: DataFrame.apply(axis=1) on an empty frame returns an empty
        # DataFrame rather than a Series, and assigning that to one score
        # column raises "Cannot set a DataFrame with multiple columns to
        # the single column ..." (ws_en_036).
        for col in required_columns if not df_inner.empty else []:
            if col in unique_columns:
                df_inner_score[f"{col}_exact_match"] = 1.0
                df_inner_msg[f"{col}_exact_match_eval_msg"] = "key_match"
                continue

            item = query.evaluation["eval_pipeline"][col]
            metric_list = item.get("metric", [])
            criterion = item.get("criterion")
            for mname in metric_list:
                if mname != "llm_judge":
                    info = df_inner.apply(
                        lambda x, m=mname, c=criterion, cc=col: _metric(
                            x[cc + "_response"], x[cc + "_query"], c, m
                        ),
                        axis=1,
                    )
                else:
                    s_list, m_list = llm_judge_column(
                        df_inner[col + "_response"].tolist(),
                        df_inner[col + "_query"].tolist(),
                        criterion, eval_model_config_name,
                    )
                    info = pd.Series(zip(s_list, m_list), index=df_inner.index)
                df_inner_score[f"{col}_{mname}"] = info.apply(lambda x: x[0])
                df_inner_msg[f"{col}_{mname}_eval_msg"] = info.apply(lambda x: x[1])

        if result_save_path is not None:
            res = pd.concat([df_inner, df_inner_score, df_inner_msg], axis=1)
            res = pd.concat([res, df_outer_wo_inner])
            res.to_csv(result_save_path, index=False)

        row_scores = df_inner_score.min(axis=1) if not df_inner_score.empty else pd.Series(dtype=float)
        tp_by_row = float(row_scores.sum()) if not row_scores.empty else 0.0
        tp_by_item = float(df_inner_score.sum().sum()) if not df_inner_score.empty else 0.0

        n_pred_rows = len(response_df)
        n_gt_rows = len(answer_df)
        n_pred_items = n_pred_rows * len(required_columns)
        n_gt_items = n_gt_rows * len(required_columns)

        precision_by_row = tp_by_row / n_pred_rows if n_pred_rows else 0.0
        recall_by_row = tp_by_row / n_gt_rows if n_gt_rows else 0.0
        precision_by_item = tp_by_item / n_pred_items if n_pred_items else 0.0
        recall_by_item = tp_by_item / n_gt_items if n_gt_items else 0.0

        def _f1(p, r):
            return 2 * p * r / (p + r) if (p + r) > 1e-9 else 0.0

        f1_by_row = _f1(precision_by_row, recall_by_row)
        f1_by_item = _f1(precision_by_item, recall_by_item)

        # Per-column metrics. df_inner_score columns are named "<col>_<metric>";
        # we collapse multiple metrics on the same col by min (a cell counts as
        # correct only if every metric on it scored 1.0).
        column_metrics: dict[str, dict[str, float]] = {}
        if not df_inner_score.empty:
            col_to_score_cols: dict[str, list[str]] = {}
            for sc_col in df_inner_score.columns:
                # last `_` separates col from metric; split on rightmost
                # known metric suffix to be robust to column names with `_`.
                base = sc_col
                for suf in ("_exact_match", "_url_match", "_in_match",
                            "_number_near", "_date_near", "_llm_judge"):
                    if sc_col.endswith(suf):
                        base = sc_col[: -len(suf)]
                        break
                col_to_score_cols.setdefault(base, []).append(sc_col)

            tp_by_col = {b: float(df_inner_score[cs].min(axis=1).sum())
                         for b, cs in col_to_score_cols.items()}
            for b, tp in tp_by_col.items():
                # Inner-merge can occasionally yield more matched rows than
                # n_pred_rows / n_gt_rows when unique_columns don't fully
                # uniquify (duplicate cross-match). Cap at 1.0 for sanity.
                p = min(tp / n_pred_rows, 1.0) if n_pred_rows else 0.0
                r = min(tp / n_gt_rows, 1.0) if n_gt_rows else 0.0
                column_metrics[b] = {
                    "precision_by_col": round(p, 4),
                    "recall_by_col": round(r, 4),
                    "f1_by_col": round(_f1(p, r), 4),
                    "tp": int(tp),
                }

        msg = df_inner_score.to_string() if not df_inner_score.empty else "no inner rows"

        # Suspicious-column detection: a column metered by ``llm_judge`` that
        # came back tp=0 across all inner rows, while at least one row has a
        # literal ``pred == target`` match, almost always indicates a failed
        # judge call (truncated JSON / parse miss) rather than a real all-miss
        # column. Surface it on stderr so re-grading is an obvious next step.
        if not df_inner_score.empty:
            for col, item in query.evaluation.get("eval_pipeline", {}).items():
                metrics_list = item.get("metric", []) or []
                if "llm_judge" not in metrics_list or col in unique_columns:
                    continue
                judge_col = f"{col}_llm_judge"
                if judge_col not in df_inner_score.columns:
                    continue
                if float(df_inner_score[judge_col].sum()) > 0:
                    continue
                resp_col, qry_col = f"{col}_response", f"{col}_query"
                if resp_col in df_inner.columns and qry_col in df_inner.columns:
                    n_literal = int((df_inner[resp_col] == df_inner[qry_col]).sum())
                else:
                    n_literal = 0
                if n_literal > 0:
                    logger.warning(
                        "[grade] %s column %r: llm_judge scored 0/%d but %d "
                        "row(s) have literally identical pred==target — likely "
                        "a failed judge call. Re-grade this column.",
                        query.instance_id, col, len(df_inner_score), n_literal,
                    )

        if (
            precision_by_item == recall_by_item == f1_by_item == 1.0
            and precision_by_row == recall_by_row == f1_by_row == 1.0
        ):
            score = 1.0

    except Exception:
        return EvaluationResult(
            instance_id=query.instance_id,
            msg=f"evaluator error:\n{traceback.format_exc()}",
        )

    cm = column_metrics if 'column_metrics' in locals() else {}
    if cm:
        n_cols = len(cm)
        p_col = sum(v["precision_by_col"] for v in cm.values()) / n_cols
        r_col = sum(v["recall_by_col"] for v in cm.values()) / n_cols
        f1_col = sum(v["f1_by_col"] for v in cm.values()) / n_cols
    else:
        p_col = r_col = f1_col = 0.0

    return EvaluationResult(
        instance_id=query.instance_id,
        score=score,
        precision_by_row=precision_by_row,
        recall_by_row=recall_by_row,
        f1_by_row=f1_by_row,
        precision_by_item=precision_by_item,
        recall_by_item=recall_by_item,
        f1_by_item=f1_by_item,
        precision_by_col=round(p_col, 4),
        recall_by_col=round(r_col, 4),
        f1_by_col=round(f1_col, 4),
        column_metrics=cm,
        msg=msg,
    )
