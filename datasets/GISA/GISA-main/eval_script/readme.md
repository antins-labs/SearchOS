## 🚀 Running the Benchmark

To run the ReAct Agent benchmark, you need to configure the `run_benchmark.sh` script with the necessary API keys and file paths.

### 1. Configuration

Open `run_benchmark.sh` and fill in the following parameters:

| Parameter | Description | Required |
| --- | --- | --- |
| **`API_KEY`** | The API Key for the LLM Agent. | Yes |
| **`BASE_URL`** | The API base URL for the LLM. Supports official platforms like OpenRouter, Volcengine (Doubao), Alibaba Cloud, DeepSeek, Kimi, etc. | Yes |
| **`MODEL_NAME`** | The name of the model to be tested. | Yes |
| **`JINA_API_KEY`** | API key for fetching web page content. | Yes |
| **`SERPER_API_KEY`** | API key for performing Google searches. | Yes |
| **`BENCHMARK_DATA_PATH`** | Path to the decrypted question file (in `.jsonl` format). | Yes |
| **`WORKERS`** | Controls the concurrency level (number of parallel workers). | Optional |
| **`ENABLE_THINKING`** | Set to `true` to enable the model's "thinking" mode (if supported). | Optional |

Since the process involves using an LLM to summarize browsed web pages, a SUMMARY Model also needs to be configured. By default, we use the non-thinking version of the same base model.

### 2. Execution

Once configured, execute the script to start the benchmark:

```bash
bash run_benchmark.sh
```

### 3. Output

The results will be saved in the `./benchmark_results/` directory, inside a folder named after your `MODEL_NAME`.

* Each question produces a separate JSON file.
* These files contain the full message history of the agent and the final prediction.



## 📊 Evaluation

To calculate metrics based on the benchmark output, run the `evaluator.py` script.

### Command

```bash
python run_evaluation.py \
  --pred_dir_path './benchmark_results/gpt5.2-thinking/' \
  --gt_dir_path './bench_data/answers/' \
  --question_file_path './bench_data/question.jsonl'

```

### Parameters

* `--pred_dir_path`: The folder containing the model's prediction files (where each file is named `{qid}.json`).
* `--gt_dir_path`: The directory containing the official ground truth answers.
* `--question_file_path`: The path to the source question file.

### Results

After running the evaluator, two files will be generated inside the `pred_dir_path`:

1. **`_all_evaluation_results.json`**: Contains detailed evaluation results for every single data point.
2. **`_final_scores.json`**: Contains the aggregated metric scores for the entire dataset.



## 🔗 Evaluating Other Frameworks

If you wish to evaluate agents from other frameworks using this system, simply organize your prediction results as follows:

1. **File Naming:** Save the prediction for each question as a separate JSON file named `{qid}.json`, where `qid` corresponds to the question ID.
2. **JSON Structure:** Each file must include a `prediction` field.
3. **Table Formatting:** If the response contains tabular data, it must be wrapped in TSV code blocks (i.e., ````tsv ... ````) for the evaluation system to parse it correctly.

**Example format for `{qid}.json`:**

```json
{
  "prediction": "Here is the data you requested:\n```tsv\nColumn1\tColumn2\nVal1\tVal2\n```"
}
```
