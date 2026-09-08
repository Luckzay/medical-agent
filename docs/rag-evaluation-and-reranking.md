# RAG 评测与 Reranker 运行手册

## 质量门禁

1. 先校验 dataset；报告必须记录 canonical SHA-256。
2. weak/synthetic 标签报告必须显示非最终结论警告。只有双人审核、冲突裁决并将 provenance 更新为 `human` 后，才可作为发布门禁。
3. 每个实验固定 model fingerprint、collection alias/generation、lexical/vector candidate limit、top_k、RRF k、reranker、seed。
4. 当前 131 条 structured rows 均等价为单 chunk；chunk budget/overlap 只记录为不适用，不做虚假优劣比较。
5. 未实际加载并执行的 embedding/reranker 候选统一记 `not_run`。

## 人工标注

使用 `load_dataset()` 读取 seed；专家核对原文和 lineage 后，通过 `add_human_judgment()` 写入 0–3 grades、annotator、method、annotated_at，再用 `save_dataset()` 输出新版本。禁止覆盖旧版本。hard negative 不得同时是 grade>0 的 relevant evidence。CI 应执行 strict model validation 并检查新 hash。

等级：0 无关；1 边缘相关；2 可支持研究目标；3 直接、核心证据。

## Provider 与资源选择

- Embedding baseline：multilingual-e5-small，固定 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`、384d。
- Embedding candidate：BGE-M3（资源较高）；未下载/未运行保持 `not_run`。
- Reranker candidate：`BAAI/bge-reranker-v2-m3`，适合多语；CPU/内存不足时应先选择更轻 cross-encoder 并单独形成 fingerprint，不得把不同模型成绩混写。
- `sentence_transformers` 只在首个实际调用中动态 import/load。单测使用 deterministic provider，不访问网络。

Embedding cache header 必须匹配完整 fingerprint 与 dimension。collection generation key 同时包含 corpus hash 和 dimension；dimension 改变必须建新 generation。

## 安全与失败策略

Reranker 输入是 canonical repository 已按 trusted tenant/project、active version、status 和 lineage 解析后的候选。rerank 后只能重排同一 ID 集合。optional provider 失败保留 fused 顺序并返回 `reranker_unavailable`；required provider 失败抛出明确错误。默认 disabled，保持历史排序。

## 参数实验

建议网格：lexical/vector candidate limit、top_k、RRF k、reranker candidate limit。排序均以 evidence ID 作最终 tie-break。报告同时保存每 query ranking/latency、aggregate JSON 和 Markdown 摘要。P95 使用 nearest-rank 定义。
