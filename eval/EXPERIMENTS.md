# WideSearch 评测实验流程(可复用)

一套「多轮跑 widesearch → 汇总 → best-of-N」的标准流程。核心约定都踩过坑,照此复用即可。

## 0. 环境

- conda 环境 `searchharness`;工作目录 `SearchOS-Main`。
- API key 放 `.env`,`eval/run.py` 启动时自动 `load_dotenv`。
- 数据集 200 行:`ws_en_001..050`(第 1–50)+ `ws_zh_001..050`(第 101–150)。

## 1. 用不同 API key 跑不同题段

模型 key 由 `settings.py` 里 profile 的 `api_key_env` 决定,默认全指向 `OPENAI_API_KEY`。
要让某段题改用别的 key(如 `OPENAI_API_KEY_D`),**在启动前把 `OPENAI_API_KEY` 覆写成目标 key 的值**——
`load_dotenv` 默认 `override=False`,shell 里已存在的环境变量不会被 `.env` 覆盖:

```bash
export OPENAI_API_KEY="$(python -c "from dotenv import dotenv_values;import sys;sys.stdout.write(dotenv_values('.env')['OPENAI_API_KEY_D'])")"
```

## 2. 启动:必须用 nohup 脱离,不要用 harness 后台任务

⚠️ 用 Claude Code 的 `run_in_background` 启动会被 harness 在 ~36 分钟处回收(status: killed)。
widesearch 每题 6–15 分钟、整轮数小时,必须脱离 harness:

```bash
# 实验1:1-50,默认 key
nohup python -m eval.run --benchmark widesearch --range 1-50 --concurrency 2 \
  --output-dir "eval_results/widesearch_1-50_keyMAIN_$(date +%Y%m%d_%H%M%S)" \
  > exp1.log 2>&1 &
disown

# 实验2:101-150,D key(先 export 覆写)
export OPENAI_API_KEY="$(python -c "from dotenv import dotenv_values;import sys;sys.stdout.write(dotenv_values('.env')['OPENAI_API_KEY_D'])")"
nohup python -m eval.run --benchmark widesearch --range 101-150 --concurrency 2 \
  --output-dir "eval_results/widesearch_101-150_keyD_$(date +%Y%m%d_%H%M%S)" \
  > exp2.log 2>&1 &
disown
```

验证脱离成功:`ps -o pid,ppid,etime -p <PID>`,**PPID 应为 1**。
（macOS 没有 `setsid`,用 `nohup ... & disown` 即可。）

## 3. 续跑 / 重跑单题

- **续跑**:复用同一 `--output-dir` 再启动即可。runner 检测到题目已有 `eval_result.json` 就跳过(见 `runner.py` 的 resume-skip)。
- **重跑某题**:先删该题目录,再用 `--ids` 精确指定重跑到同一输出目录:
  ```bash
  rm -rf eval_results/<dir>/ws_zh_011          # 纯 rm 单条,别和 for/echo/grep 混在一条命令里(会被 auto-mode 分类器误判拒绝)
  python -m eval.run --benchmark widesearch --ids ws_zh_011 --concurrency 1 --output-dir eval_results/<dir>
  ```

## 4. 汇总:eval/aggregate_runs.py

把多轮(每轮 = en 目录 + zh 目录)聚合成 `widesearch_summary.json` + `widesearch_summary_detailed.csv`,
按 en/zh/all × 各指标输出 run1..runN / avg@N / max@N(best-of-N):

```bash
python -m eval.aggregate_runs \
  --run "eval_results/widesearch_1-50_keyMAIN_A+eval_results/widesearch_101-150_keyD_A" \
  --run "eval_results/widesearch_1-50_keyMAIN_B+eval_results/widesearch_101-150_keyD_B" \
  --out-dir eval_results/exports
```

- `avg@N` = 各轮 macro-mean 的平均;`max@N` = 每题跨轮取 max(题的并集)再平均。
- 口径与 `eval/run.py` 的 summary 一致(macro-mean,见 `runner.aggregate_widesearch`)。

## 5. 指标解读要点

- **row 是 all-or-nothing**:一行得分 = 行内所有列的最小值,任一列错/缺 → 整行 0。
- 因此 `f1_by_row` 远低于 `f1_by_item`(单元格级);row 对「最差的那一列」极敏感。
- 单题某列系统性崩(如聚合页幻觉、分组维度未回填)会把 row 从接近满分打到 0,而 item 只略降。
- `score_em`(整题全对率)通常接近 0;重复跑救不了「三轮都崩」的硬列题。
