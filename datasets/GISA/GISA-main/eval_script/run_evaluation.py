import pandas as pd
import numpy as np
import re
import math
import json
import os
from io import StringIO
from typing import List, Optional, Tuple, Union, Dict, Any
from collections import Counter
import difflib
import random
import argparse

class SimpleEvaluator:
    def _normalize_val(self, val: Union[str, int, float]) -> str:
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ['nan', 'none', 'null']:
            return ""

        clean_num = val_str.replace(',', '').replace('$', '')
        is_percent = False
        if clean_num.endswith('%'):
            is_percent = True
            clean_num = clean_num[:-1]
            
        try:
            f_val = float(clean_num)
            if is_percent:
                f_val /= 100.0
            
            if f_val.is_integer():
                return str(int(f_val))
            else:
                formatted = "{:.6f}".format(f_val).rstrip('0').rstrip('.')
                return formatted if formatted else "0"
        except ValueError:
            pass
            
        normed = val_str.lower().replace(" ", "").replace("*", "").replace("\n", "")
        return normed

    def _extract_model_output(self, model_output: str) -> Optional[pd.DataFrame]:
        pattern = r"```(?:tsv)?\s*(.*?)```"
        match = re.search(pattern, model_output, re.DOTALL)
        
        if match:
            raw_content = match.group(1)
        else:
            raw_content = model_output
        try:
            # 过滤掉空行
            raw_content = "\n".join([line for line in raw_content.split('\n') if line.strip()])
            if not raw_content: return None

            output = pd.read_csv(StringIO(raw_content), sep="\t")
            output.columns = [str(col).strip().lower().replace(" ", "") for col in output.columns]
            output = output.map(self._normalize_val)
        except Exception as e:
            print(f"Extract Error: {e}")
            output = None
        return output    

    def load_ground_truth(self, file_path: str, question_type: str = 'table') -> pd.DataFrame:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"GT file not found: {file_path}")
        if question_type != "table":
            header = None
        else:
            header = 'infer'
        
        try:
            df = pd.read_csv(file_path, header=header)
        except Exception as e:
            if 'codec' in str(e):
                df = pd.read_csv(file_path, header=header, encoding='gbk')
            else:
                raise e
            
        # 统一列名为字符串
        df.columns = [str(col).strip().lower().replace(" ", "") for col in df.columns]
        df = df.map(self._normalize_val)
        return df


    def _calculate_f1(self, tp: int, n_pred: int, n_gt: int) -> Tuple[float, float, float]:
        precision = tp / n_pred if n_pred > 0 else 0.0
        recall = tp / n_gt if n_gt > 0 else 0.0
        if (precision + recall) == 0:
            f1 = 0.0
        else:
            f1 = 2 * (precision * recall) / (precision + recall)
        return precision, recall, f1

    def flatten_table(self, df: pd.DataFrame):
        items = []
        for col in df.columns:
            values = df[col]
            for val in values:
                items.append((col, val))
        return items

    def evaluate_item(self, pred_df: pd.DataFrame, gt_df: pd.DataFrame) -> dict:
        if pred_df is None or pred_df.empty:
            return {"item_em": 0}

        pred_item = "".join(pred_df.iloc[0,:].tolist())
        gt_item = "".join(gt_df.iloc[0,:].tolist())
        
        is_match = 1 if pred_item == gt_item else 0
        return {"item_em": is_match}
        
    def evaluate_set(self, pred_df: pd.DataFrame, gt_df: pd.DataFrame) -> dict:
        if pred_df is None or pred_df.empty:
            return {"set_precision": 0.0, "set_recall": 0.0, "set_f1": 0.0}

        pred_set = set(pred_df.iloc[:,-1].tolist())
        gt_set = set(gt_df.iloc[:,-1].tolist())

        tp = len(pred_set.intersection(gt_set))
        p, r, f1 = self._calculate_f1(tp, len(pred_set), len(gt_set))

        return { "set_precision": p, "set_recall": r, "set_f1": f1}

    def evaluate_list(self, pred_df: pd.DataFrame, gt_df: pd.DataFrame) -> dict:
        if pred_df is None or pred_df.empty:
            return {"list_content_f1": 0.0, "list_order_score": 0.0}

        pred_list = pred_df.iloc[:,-1].tolist()
        gt_list = gt_df.iloc[:,-1].tolist()
        
        gt_counter = Counter(gt_list)
        pred_counter = Counter(pred_list)
        
        intersection = gt_counter & pred_counter 
        num_common = sum(intersection.values())
        
        len_gt = len(gt_list)
        len_pred = len(pred_list)
        
        if len_pred == 0:
            precision = 0.0
        else:
            precision = num_common / len_pred
            
        if len_gt == 0:
            recall = 0.0
        else:
            recall = num_common / len_gt
            
        if (precision + recall) == 0:
            content_f1 = 0.0
        else:
            content_f1 = 2 * (precision * recall) / (precision + recall)

        matcher = difflib.SequenceMatcher(None, gt_list, pred_list)
        order_score = matcher.ratio()

        return {
            "list_content_f1": round(content_f1, 4),
            "list_order_score": round(order_score, 4)
        }

    def evaluate_table(self, pred_df: pd.DataFrame, gt_df: pd.DataFrame) -> dict:
        default_res = {
            "table_row_f1": 0.0, "table_row_precision": 0.0, "table_row_recall": 0.0,
            "table_item_f1": 0.0, "table_item_precision": 0.0, "table_item_recall": 0.0
        }
        
        if pred_df is None or pred_df.empty:
             return default_res.copy()

        common_cols = [c for c in gt_df.columns if c in pred_df.columns]
        
        if not common_cols:
            row_p, row_r, row_f1 = 0.0, 0.0, 0.0
        else:
            pred_rows = set(tuple(row) for row in pred_df[common_cols].fillna('__NAN__').astype(str).to_numpy())
            gt_rows = set(tuple(row) for row in gt_df[common_cols].fillna('__NAN__').astype(str).to_numpy())
            
            tp_rows = len(pred_rows.intersection(gt_rows))
            row_p, row_r, row_f1 = self._calculate_f1(tp_rows, len(pred_rows), len(gt_rows))

        pred_items = self.flatten_table(pred_df)
        gt_items = self.flatten_table(gt_df)

        pred_counter = Counter(pred_items)
        gt_counter = Counter(gt_items)

        intersection = pred_counter & gt_counter
        tp_items = sum(intersection.values())

        n_pred_items = sum(pred_counter.values()) 
        n_gt_items = sum(gt_counter.values())     

        item_p, item_r, item_f1 = self._calculate_f1(tp_items, n_pred_items, n_gt_items)


        return {
            "table_row_f1": row_f1,  
            "table_row_precision": row_p,
            "table_row_recall": row_r,
            "table_item_f1": item_f1,
            "table_item_precision": item_p,
            "table_item_recall": item_r
        }


    def evaluate_one(self, prediction: str, gt_path: str, question_type: str, qid=None) -> dict:
        if prediction.endswith(".csv"):
            pred_df = self.load_ground_truth(prediction, question_type=question_type.lower())
        else:
            pred_df = self._extract_model_output(prediction)
        if pred_df is None:
            print(f"qid:{qid} prediction is empty")

        gt_df = self.load_ground_truth(gt_path, question_type=question_type.lower())
        
        q_type = question_type.lower()
        if q_type == 'item':
            metrics = self.evaluate_item(pred_df, gt_df)
        elif q_type == 'set':
            metrics = self.evaluate_set(pred_df, gt_df)
        elif q_type == 'list':
            metrics = self.evaluate_list(pred_df, gt_df)
        elif q_type == 'table':
            metrics = self.evaluate_table(pred_df, gt_df)
        else:
            print(f"Unknown question type: {question_type}, treating as item")
            metrics = self.evaluate_item(pred_df, gt_df)
        if pred_df is not None:
            if q_type != 'set':
                metrics['global_em'] =  int(np.array_equal(pred_df.to_numpy(), gt_df.to_numpy()))
            else:
                pred_set = set(pred_df.iloc[:, 0].tolist())
                gt_set = set(gt_df.iloc[:, 0].tolist())
                metrics['global_em'] =  int(pred_set == gt_set)
        else:
            metrics['global_em'] = 0
        metrics['question_type'] = question_type
        

        return metrics

    def run_evaluation(self, pred_dir_path: str, gt_dir_path: str, question_file_path: str):
        id2item = {}
        with open(question_file_path, 'r', encoding='utf-8') as f:
            question_list = [json.loads(line) for line in f.readlines()]
        print(f"all question total: {len(question_list)}")
        for q_item in question_list:
            id2item[q_item['id']] = {"q_item": q_item}

        for file in os.listdir(pred_dir_path):
            if file.endswith('.json') and not file.startswith('_'):
                with open(os.path.join(pred_dir_path, file), 'r', encoding='utf-8') as f:
                    pred = json.load(f)
                # qid = pred['question_item']['id']
                qid = file.split(".")[0]
                gt_file_path = os.path.join(gt_dir_path, f'{qid}.csv')
                
                if qid not in id2item:
                    print(f"qid {qid} not in question_list")
                    continue
                
                q_type = id2item[qid]['q_item']['answer_type']
                pred['qid'] = qid
                pred['q_type'] = q_type
                pred['gt_file_path'] = gt_file_path
                id2item[qid]['pred_item'] = pred
            elif file.endswith(".csv"):
                qid = int(file.split(".")[0])
                gt_file_path = os.path.join(gt_dir_path, f'{qid}.csv')
                if qid not in id2item:
                    print(f"qid {qid} not in question_list")
                    continue
                q_type = id2item[qid]['q_item']['answer_type']
                file_path = os.path.join(pred_dir_path, file)
                pred = {"prediction": file_path}
                id2item[qid]['pred_item'] = pred
        if 'human_performance' in pred_dir_path:
            remain_keys = []
            for k,v in id2item.items():
                if 'pred_item' in v:
                    remain_keys.append(k)
            id2item = {k: v for k, v in id2item.items() if k in remain_keys}

        for qid, item_dict in id2item.items():
            if 'pred_item' not in item_dict:
                print(f"qid: {qid} missing answer file!")    
        print("--------")

        for qid, item_dict in id2item.items():
            q_item = item_dict['q_item']
            gt_file_path = os.path.join(gt_dir_path, f'{qid}.csv')
            metrics = self.evaluate_one(
                prediction=item_dict.get('pred_item',{}).get('prediction', ""),
                gt_path=gt_file_path,
                question_type=q_item['answer_type'],
                qid=qid
            )
            item_dict['metrics'] = metrics

        result_summary = self.gather_results([item_dict['metrics'] for item_dict in id2item.values()])
        
        all_save_path = os.path.join(pred_dir_path, '_all_evaluation_results.json')
        score_save_path = os.path.join(pred_dir_path, '_final_scores.json')
        with open(all_save_path, 'w', encoding='utf-8') as f:
            json.dump(id2item, f, ensure_ascii=False, indent=4)
        with open(score_save_path, 'w', encoding='utf-8') as f:
            json.dump(result_summary, f, ensure_ascii=False, indent=4)
        return result_summary
    

    def gather_results(self, score_list: List[dict]):
        df = pd.DataFrame(score_list)
        overall_em = df['global_em'].mean()
        type_report = df.groupby('question_type').mean().round(4)
        detail_score_dict = type_report.to_dict(orient='index')
        count_by_type = df['question_type'].value_counts().to_dict()

        summary = {}
        summary['overall_global_em'] = overall_em
        for type in count_by_type:
            type_result = {'num_samples': count_by_type[type], **{f"overall_{k}": round(v, 4) for k, v in detail_score_dict[type].items() if not pd.isna(v)}}
            summary[type] = type_result
        
        print(json.dumps(summary, ensure_ascii=False, indent=4))
        return summary




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred_dir_path", type=str, required=True)
    parser.add_argument("--gt_dir_path", type=str, required=True)
    parser.add_argument("--question_file_path", type=str, required=True)
    args = parser.parse_args()

    evaluator = SimpleEvaluator()
    evaluator.run_evaluation(
        pred_dir_path=args.pred_dir_path,
        gt_dir_path=args.gt_dir_path,
        question_file_path=args.question_file_path
    )
    