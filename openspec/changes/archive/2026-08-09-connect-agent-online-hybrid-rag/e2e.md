# 真实 Agent E2E 记录

- 时间：2026-08-09 17:05 CST
- 输入药材：当归
- research goal：研究当归阿魏酸的超分子自组装机制与实验条件
- 执行入口：`LangGraphAnalysisWorkflow.invoke`（完整七节点，不是检索 CLI）
- Qdrant：Server 1.15.4，alias `medical_evidence_active`，131 points
- Embedding：`intfloat/multilingual-e5-small` revision
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`，384 维，Cosine，L2，E5 前缀
- 总耗时：6441.78 ms
- retrieval mode：`hybrid`
- retrieval latency：6364.10 ms
- degraded reason：无
- 七节点：normalize → discover → chemistry → evidence → proposal → review → finalize

## 实际检索证据

返回 10 条 literature evidence：`literature:EN:72`、`literature:EN:19`、
`literature:EN:114`、`literature:EN:83`、`literature:EN:66`、
`literature:EN:84`、`literature:EN:50`、`literature:EN:73`、
`literature:EN:44`、`literature:EN:85`。另有种子证据
`seed:当归:ferulic-acid`。

首条 fused 结果 `literature:EN:72`：lexical rank 19、vector rank 2、fused rank 1。
另一个可见交叉通道样例 `literature:EN:73`：lexical rank 2、vector rank 34、
fused rank 8。所有 diagnostics 的 mode 均为 hybrid，embedding fingerprint 与固定模型一致，
且 degraded reason 均为空。

## Proposal 引用完整性

Proposal 实际引用：`literature:EN:114`、`literature:EN:19`、
`literature:EN:44`、`literature:EN:83`、`literature:EN:84`、
`literature:EN:85`、`seed:当归:ferulic-acid`。

上述引用全部属于最终 AnalysisResult evidence 集，引用完整性检查结果为 `true`。
Reviewer 状态为 `needs_revision`，属于实验条件完整性与探索性默认值提示，不是引用缺失。
