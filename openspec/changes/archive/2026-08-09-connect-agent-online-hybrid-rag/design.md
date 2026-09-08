## Context

Qdrant alias `medical_evidence_active` 与 canonical SQLite 已由上一迭代建立。当前 wiring 分散且 builtin tool 未实例化 HybridRetriever。

## Goals / Non-Goals

**Goals:** 一个惰性共享 runtime；独立 lexical/vector 召回、RRF、精确字段增强、lineage 校验；模式化失败语义；可审计 diagnostics。

**Non-Goals:** 更换 embedding 模型、改变七节点顺序或 Evidence ID 外部格式。

## Decisions

1. Query Builder 生成 lexical/vector 两种确定性查询，并单独保留 DOI/SMILES。
2. EvidenceRetrievalService 是 Tool、MCP、workflow 与诊断 API 的唯一 wiring 入口。
3. scope 以受信执行上下文为准；请求字段只用于无内部 scope 的兼容入口。
4. disabled 不构造向量 runtime；optional 捕获 provider/Qdrant 故障并标注原因；required 抛出明确错误。
5. Qdrant 返回 chunk ID 后必须经 canonical repository 重新解析 active ready lineage，broken lineage 不进入结果。

## Risks / Trade-offs

- 首次真实查询加载模型产生冷启动；通过 lazy load 避免 import/startup 下载。
- lexical 与 vector 候选不重合时需 canonical 映射；无法解析的候选宁可排除。
