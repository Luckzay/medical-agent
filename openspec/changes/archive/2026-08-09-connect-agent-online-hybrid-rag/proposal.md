## Why

托管向量基础设施已具备，但 Agent 的 `search_literature` 与 evidence 节点仍停留在 FTS5，线上无法获得真实语义召回，也无法按模式可靠降级。

## What Changes

- 以共享 Evidence Retrieval Service 接入真实 Qdrant、惰性 E5 embedding、FTS5、canonical lineage 与 RRF。
- 扩展工具兼容 schema、确定性 Query Builder、租户/项目强制过滤及检索诊断。
- Tool/MCP/LangGraph/管理诊断统一复用 runtime；保持七节点及旧调用兼容。
- 明确 disabled/optional/required 语义，更新契约、文档与测试。

## Capabilities

### Modified Capabilities
- `hybrid-evidence-retrieval`: 从基础能力升级为 Agent 在线 RAG 的正式执行路径。

## Impact

影响 Python Agent 的 evidence/tool/workflow/runtime、OpenAPI、配置与运维文档；不改变旧 Evidence ID、Proposal/Reviewer 引用约束。
