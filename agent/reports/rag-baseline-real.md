# RAG 离线评测报告

> **警告：当前 seed 含 weak/synthetic 标签，指标仅用于管线基线，不是最终质量结论。**

- Dataset: `tcm-literature-seed-v1` / `a9d60d5c283da5e75d2a649a70ac79851148da4b9c7d292c49c7b84cdc4c5576`
- Model: `sentence_transformers:intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3:d384:l2`
- Collection: `medical_evidence_active` / `20260809054053`
- Seed: `20260809`

| Mode | Status | Recall@10 | MRR@10 | nDCG@10 | Avg/P95 ms |
|---|---|---:|---:|---:|---:|
| lexical | completed | 1.0000 | 1.0000 | 1.0000 | 1.683/2.692 |
| vector | completed | 1.0000 | 0.8667 | 0.8978 | 2456.301/14659.533 |
| hybrid_rrf | completed | 1.0000 | 1.0000 | 1.0000 | 14.654/20.404 |
| hybrid_reranker | not_run | 0.0000 | 0.0000 | 0.0000 | 0.000/0.000 |

## 候选模型状态

- `BAAI/bge-m3`: `not_run`
- `BAAI/bge-reranker-v2-m3`: `not_run`

未实际运行的候选模型不包含成绩。
