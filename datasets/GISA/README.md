---
license: apache-2.0
task_categories:
- question-answering
- text-generation
language:
- en
tags:
- agent
size_categories:
- n<1K
---
# GISA: A Benchmark for General Information-Seeking Assistant</h1>

<p>
<a href="https://github.com/RUC-NLPIR/GISA/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache-blue" alt="license"></a>
<a href="https://arxiv.org/abs/2602.08543"><img src="https://img.shields.io/badge/Paper-Arxiv-red"></a>
<a href="https://huggingface.co/spaces/RUC-NLPIR/GISA-LeaderBoard"><img src="https://img.shields.io/badge/Leaderboard-GISA-orange"></a>
</p>

**Authors**: Yutao Zhu, Xingshuo Zhang, Maosen Zhang, Jiajie Jin, Liancheng Zhang, Xiaoshuai Song, Kangzhi Zhao, Wencong Zeng, Ruiming Tang, Han Li, Ji-Rong Wen, and Zhicheng Dou

## Benchmark Highlights
GISA is a benchmark for General Information-Seeking Assistants with 373 human-crafted queries that reflect real-world information needs. It includes both stable and live subsets, four structured answer formats (item, set, list, table), and complete human search trajectories for every query.
- **Diverse answer formats with deterministic evaluation.**  
  GISA uses four structured answer types (item, set, list, table) with strict matching metrics for reproducible evaluation, avoiding subjective LLM judging while preserving task diversity.
- **Unified deep + wide search capabilities.**  
  Tasks require both vertical reasoning and horizontal information aggregation across sources, evaluating long-horizon exploration and summarization in one benchmark.
- **Dynamic, anti-static evaluation.**  
  Queries are split into stable and live subsets; the live subset is periodically updated to reduce memorization and keep the benchmark challenging over time.
- **Process-level supervision via human trajectories.**  
  Full human search trajectories are provided for every query, serving as gold references for process reward modeling and imitation learning while validating task solvability.

## Evaluation
Please refer to our [GitHub](https://github.com/RUC-NLPIR/GISA).

## Data Schema

#### 1. encrypted_question.jsonl
Each row contains:

- id (int): the ID of the question (it is **not** continuous)
- question (str): the question after encryption
- answer_type (str): the type of the answer, can be item, set, list, or table
- question_type (str): the type of the question, can be stable or live
- topic (str): the topic of the question, can be TV Shows \& Movies, Science \& Technology, Art, History, Sports, Music, Video Games, Geography, Politics, or Other
- canary (str): the password used for decryption
  
#### 2. answer/[id].csv
The file contains the answer corresponds to the question [id].

#### 3. trace/[id].json
The file conatins the human trajectory of the question [id], with the following keys:

- search (list): the queries issued by the annotator
- result (dict): the search result of each query
- click (list): the click behaviors made by the annotator

## Loading Method

```python
def derive_key(password: str, length: int) -> bytes:
    hasher = hashlib.sha256()
    hasher.update(password.encode())
    key = hasher.digest()
    return key * (length // len(key)) + key[: length % len(key)]

def decrypt(ciphertext_b64: str, password: str) -> str:
    encrypted = base64.b64decode(ciphertext_b64)
    key = derive_key(password, len(encrypted))
    decrypted = bytes(a ^ b for a, b in zip(encrypted, key))
    return decrypted.decode()

obj["question"] = decrypt(str(obj["question"]), str(obj["canary"]))
```


## Citation
```bibtex
@article{GISA,
  title      = {GISA: A Benchmark for General Information Seeking Assistant},
  author     = {Yutao Zhu and
                Xingshuo Zhang and
                Maosen Zhang and
                Jiajie Jin and
                Liancheng Zhang and
                Xiaoshuai Song and
                Kangzhi Zhao and
                Wencong Zeng and
                Ruiming Tang and
                Han Li and
                Ji-Rong Wen and
                Zhicheng Dou},
  journal    = {CoRR},
  volume     = {abs/2602.08543},
  year       = {2026},
  url        = {https://doi.org/10.48550/arXiv.2602.08543},
  doi        = {10.48550/ARXIV.2602.08543},
  eprinttype = {arXiv},
  eprint     = {2602.08543}
}

