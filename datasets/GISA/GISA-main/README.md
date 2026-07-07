<h1 align="center">GISA: A Benchmark for General Information-Seeking Assistant</h1>

<div align="center"> 
<p>
<a href="https://github.com/RUC-NLPIR/GISA/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache-blue" alt="license"></a>
<a href="https://arxiv.org/abs/2602.08543"><img src="https://img.shields.io/badge/Paper-Arxiv-red"></a>
<a href="https://huggingface.co/datasets/RUC-NLPIR/GISA"><img src="https://img.shields.io/badge/Datasets-%F0%9F%A4%97%20Hugging%20Face-8A2BE2"></a>
<!-- <a href="https://huggingface.co/spaces/RUC-NLPIR/GISA-LeaderBoard"><img src="https://img.shields.io/badge/Leaderboard-%F0%9F%A4%97%20Hugging%20Face-8A2BE2"></a> -->
<a href="https://huggingface.co/spaces/RUC-NLPIR/GISA-LeaderBoard"><img src="https://img.shields.io/badge/Leaderboard-GISA-orange"></a>
</p>
</div>

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

<div align=center>
<img src="https://github.com/RUC-NLPIR/GISA/blob/main/fig/overview.jpg">
</div>

## Evaluation
Please follow the instruction in `eval_script` for evaluation.

## Submission
Please send your results to yutaozhu94 AT gmail.com or use [HuggingFace leaderboard submission system](https://huggingface.co/spaces/RUC-NLPIR/GISA-LeaderBoard). We will merge approved results periodically.

## Citation
```bibtex
@article{GISA,
  title     = {GISA: A Benchmark for General Information Seeking Assistant},
  author    = {Yutao Zhu and
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
