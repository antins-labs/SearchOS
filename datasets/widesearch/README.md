---
license: other
language:
- zh
- en
size_categories:
- n<1K
configs:
- config_name: default
  data_files:
  - split: full
    path: "widesearch.jsonl"
---
# WideSearch: Benchmarking Agentic Broad Info-Seeking

## Dataset Summary

WideSearch is a benchmark designed to evaluate the capabilities of Large Language Model (LLM) driven agents in **broad information-seeking** tasks. Unlike existing benchmarks that focus on finding a single, hard-to-find fact, WideSearch assesses an agent's ability to handle tasks that require gathering a large amount of scattered, yet easy-to-find, information.

The challenge in these tasks lies not in cognitive difficulty, but in the operational scale, repetitiveness, and the need for **Completeness** and **Factual Fidelity** in the final result. For example, a financial analyst gathering key metrics for all companies in a sector, or a job seeker collecting every vacancy that meets their criteria.

The benchmark, originating from the research paper "WideSearch: Benchmarking Agentic Broad Info-Seeking," contains 200 meticulously designed tasks (100 in English, 100 in Chinese).

See our [paper](https://arxiv.org/abs/2508.07999) and [github repo](https://github.com/ByteDance-Seed/WideSearch) for more details.

## Dataset Structure

The dataset consists of these components: a task file, and a directory containing the ground-truth answers.

```

/
├── widesearch.jsonl
└── widesearch_gold/
  ├── ws_en_001.csv
  ├── ws_zh_001.csv
  └── ...

```

### Data Instances

`widesearch.jsonl` is JSON Lines file, where each line represents a single task.

**Example:**

```json
{
    "instance_id": "ws_en_001",
    "query": "My son is about to start his university applications but he\u2019s still uncertain about both his major and which universities to apply to. Could you help me find the top five universities in each of the five broad subjects from the QS World University Rankings by Subject 2025, and also check their standings in the QS World University Rankings 2025 and the Times Higher Education World University Rankings 2025? And I need the home page of the university's official website, standard application deadline for regular decision as well as the application fee without the fee waiver.Please organize the results in one Markdown table with the following columns:\nSubject, University, QS World University Rankings by Subject 2025, QS World University Rankings 2025, Times Higher Education  World University Rankings 2025, Home Page, Application Deadline, Application Fee\nPlease use the universities\u2019 full official names in English. \nUse only Arabic numerals in the ranking, for example: 1.\n\nThe output format is ```markdown\n{data_content}\n```.",
    "evaluation": "{\"unique_columns\": [\"subject\", \"university\"], \"required\": [\"subject\", \"university\", \"qsworlduniversityrankingsbysubject2025\", \"qsworlduniversityrankings2025\", \"timeshighereducationworlduniversityrankings2025\", \"homepage\", \"applicationdeadline\", \"applicationfee\"], \"eval_pipeline\": {\"applicationdeadline\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"llm_judge\"], \"criterion\": \"It is sufficient if the semantics are approximately the same as the reference answer or if they point to the same entity. There is no need for a word-for-word correspondence.\\nThe month and day must be correct\"}, \"applicationfee\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"llm_judge\"], \"criterion\": \"It is sufficient if the semantics are approximately the same as the reference answer or if they point to the same entity. There is no need for a word-for-word correspondence.\\nIf there are multiple fees in the reference answer, all must be included.\"}, \"homepage\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"url_match\"]}, \"subject\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}, \"university\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}, \"qsworlduniversityrankingsbysubject2025\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}, \"qsworlduniversityrankings2025\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}, \"timeshighereducationworlduniversityrankings2025\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}}}",
    "language": "en"
}
```

```json
{
    "instance_id": "ws_zh_001",
    "query": "我要做电影研究，需要你列出来2020年-2024年（包含2020年和2024年）每年中国、美国本国票房前五的电影，表头需要包括年份、国家（如中国、美国）、电影名、导演、本国整体累计票房收益（不局限于当年，以亿为单位，保留到小数点后一位，例如7.9亿元，需要带上各国货币单位，中国电影以亿元为单位，美国电影为亿美元为单位）、电影类型。请以Markdown表格的格式输出整理后的数据，全部输出采用中文。请注意，对于当年12月末上映的电影、大部分票房收益落在下一年的，视为下一年的电影。请以Markdown表格的格式输出整理后的数据。\n表格中的列名依次为：\n年份、国家、电影名、导演、本国累计票房收益、电影类型\n\n格式为```markdown\n{数据内容}\n```。",
    "evaluation": "{\"unique_columns\": [\"国家\", \"电影名\"], \"required\": [\"年份\", \"国家\", \"电影名\", \"导演\", \"本国累计票房收益\", \"电影类型\"], \"eval_pipeline\": {\"国家\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}, \"年份\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"exact_match\"]}, \"本国累计票房收益\": {\"preprocess\": [\"extract_number\"], \"metric\": [\"number_near\"], \"criterion\": 0.1}, \"导演\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"llm_judge\"], \"criterion\": \"和参考答案语义相同大致、或者指向的实体一致即可，不需要字字对应。\\n答出子集且未答出参考答案以外的内容时可算正确\"}, \"电影类型\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"llm_judge\"], \"criterion\": \"和参考答案语义相同大致、或者指向的实体一致即可，不需要字字对应。\\n答出参考答案中的部分类型（即子集）即视为正确、基于权威来源及官方依据的类型标注同样正确、答出其中一个子集其他类型内容合理也视为正确。\"}, \"电影名\": {\"preprocess\": [\"norm_str\"], \"metric\": [\"llm_judge\"], \"criterion\": \"和参考答案语义相同大致、或者指向的实体一致即可，不需要字字对应。\"}}}",
    "language": "zh"
}
```


### Data Fields

  * `instance_id` (string): A unique identifier for the task. This ID corresponds to the filename of the ground-truth CSV file in the `widesearch_gold` directory (e.g., `ws_en_001` corresponds to `ws_en_001.csv`).
  * `query` (string): The natural language instruction given to the AI agent. It details the task requirements, the data columns to be collected, and the final Markdown table format.
  * `evaluation` (string): A string representation of an object containing all the information necessary for automated evaluation.
      * `unique_columns` (list): The primary key column(s) used to uniquely identify a row in the table.
      * `required` (list): All column names that must be present in the agent's generated response.
      * `eval_pipeline` (dict): Defines the evaluation method for each column.
          * `preprocess` (list): Preprocessing steps to be applied to the cell data before evaluation (e.g., `norm_str` to normalize strings, `extract_number` to extract numbers).
          * `metric` (list): The metric used to compare the predicted value with the ground truth (e.g., `exact_match`, `number_near` for numerical approximation, `llm_judge` for judgment by an LLM).
          * `criterion` (float or string): Specific criteria for the metric. For `number_near`, this is the allowed relative tolerance; for `llm_judge`, it's the scoring guide for the "judge" LLM.
  * `language` (string): The language of the task (`en` or `zh`).

### Ground Truth Data

The `widesearch_gold/` directory contains the ground-truth answers for each task, stored in CSV format. Filenames correspond to the `instance_id`. These files were created by human experts through exhaustive web searches and cross-validation, representing a high-quality "gold standard".

## Citation

If you use this dataset in your research, please cite the following paper:

```bibtex
@misc{wong2025widesearchbenchmarkingagenticbroad,
      title={WideSearch: Benchmarking Agentic Broad Info-Seeking}, 
      author={Ryan Wong and Jiawei Wang and Junjie Zhao and Li Chen and Yan Gao and Long Zhang and Xuan Zhou and Zuo Wang and Kai Xiang and Ge Zhang and Wenhao Huang and Yang Wang and Ke Wang},
      year={2025},
      eprint={2508.07999},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2508.07999}, 
}
```