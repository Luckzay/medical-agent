# 托管向量知识库运维指南

## 安全默认与模式

`AGENT_VECTOR_MODE=disabled` 是默认值，服务仅使用 Elasticsearch 词法检索。`optional` 在 Qdrant 或 Embedding 不可用时继续词法检索并返回 degraded diagnostics；`required` 用于通过上线门禁后的环境，依赖不健康时 readiness 必须失败。

生产 Embedding 通过配置选择。开发推荐候选为 `intfloat/multilingual-e5-small`，但这不是未经评测的生产结论。模型、revision、维度、归一化与指令模板均进入 fingerprint；任一变化都要求新 collection generation。

## 本地运行

```bash
cd agent
uv sync --locked                         # lexical-only，不安装模型
uv sync --locked --extra embedding       # 仅需要真实本地 embedding 时
uv run uvicorn app.main:app
```

启动私有网络 Qdrant：

```bash
docker compose --profile vector up -d qdrant agent
AGENT_VECTOR_MODE=optional
```

Qdrant 不向宿主机发布端口，持久化卷为 `qdrant_data`。测试使用 `QdrantClient(":memory:")` 与 deterministic test embedding，不下载模型、不使用随机向量。

## 数据准备

Canonical 文档和版本元数据写入 MySQL。毒理索引通过以下命令从业务 MySQL 读取记录并构建 Elasticsearch；如需向量检索，可追加 `qdrant` target：

```bash
uv run python -m app.scripts.build_toxicology_index --targets elasticsearch,qdrant
```

命令按 source snapshot 与 generation 可重复执行，并在校验成功后原子切换索引 alias。

## Rebuild、Rollback 与 Reconcile

管理端点均要求 `X-Agent-Token`、`X-Tenant-ID`、`X-Project-ID`、`X-Agent-Permissions`；mutation 还要求 `Idempotency-Key`。

- `POST /internal/v1/evidence/indexes/rebuild`：构建候选 generation，验证 count、lineage 与 smoke search 后才切 alias。
- `POST /internal/v1/evidence/indexes/rollback`：将 read alias 原子切回上一健康 generation，不重新 embedding。
- `POST /internal/v1/evidence/indexes/reconcile`：按 ownership scope 比较 canonical ready chunks 与 point，移除孤儿点。
- `GET /internal/v1/evidence/indexes/status`：查看模式、manifest 和 degraded 状态。

紧急回滚：将 Elasticsearch read alias 原子切回上一健康 generation；canonical MySQL 记录不受影响。

## Shadow 与质量门禁

Shadow 比较应针对 Elasticsearch 词法结果与 hybrid 结果执行，并只记录安全 diagnostics。`agent_results_changed` 必须为 false。只有 evaluation fixture 的 Recall@K、MRR、exact DOI/SMILES、删除与权限隔离全部达到记录阈值后，才能从 disabled 升为 optional/hybrid；当前默认保持 disabled。

## 安全与可观测性

权限过滤在 repository 与 retrieval channel 内执行，不依赖 route 后过滤。Qdrant payload 只含 scope、lineage、status、content hash 与 generation；不含凭据或完整外部请求。日志只记录 stage、状态、延迟和安全标识。指标覆盖 ingestion stage latency、queue depth、embedding calls、point counts、retrieval channels、degraded mode 与 reconciliation drift。

## 已知限制

首轮 parser 仅覆盖 Excel structured rows、纯文本和 Markdown；不含 PDF/Word/OCR。Token 计数采用确定性空白 token 近似。真实模型首次显式使用时可能下载权重。生产模型和最终 chunk 参数仍须评测后决定。

## 文件职责

- `app/models/knowledge.py`：canonical lifecycle、manifest、diagnostics 模型。
- `app/services/knowledge_repository.py`：MySQL source of truth 与 scope enforcement。
- `app/services/document_processing.py`：parser registry 与 structure-first chunking。
- `app/services/embeddings.py`：lazy real provider 与 deterministic test provider。
- `app/services/vector_index.py`：Qdrant collections、alias、rebuild、rollback、reconcile。
- `app/services/ingestion.py`：可恢复 ingestion state machine。
- `app/services/hybrid_retrieval.py`：lexical/vector channels 与 deterministic RRF。
- `app/api/management.py`：authenticated management APIs。
- `app/scripts/migrate_literature.py`：131 条 legacy migration。
- `app/scripts/shadow_retrieval.py`：shadow comparison。


## Agent 在线混合检索运行策略

Agent 0.8.0 起，生产查询通过共享 `EvidenceRetrievalService` 执行，不允许 CLI、API、Tool
各自构造 Qdrant client。`search_literature` 与 LangGraph evidence 节点会记录 lexical rank、
vector rank、fused rank、embedding fingerprint、延迟和降级原因。

推荐生产使用 `AGENT_VECTOR_MODE=required`；开发机允许 `optional`。告警应覆盖
`degraded=true`、`RequiredVectorUnavailable`、broken lineage 和 alias point count 异常。
诊断 API 必须携带 Agent token、`X-Tenant-ID`、`X-Project-ID` 及 `indexes:manage` 权限；
header scope 优先于请求内容。模型只在第一次向量查询时惰性加载，服务 import/startup 不下载。

验证完整 Agent 时必须调用七节点 workflow，并检查：节点顺序未变、mode 为 hybrid、每条文献
Evidence ID 可解析、proposal 引用均属于最终 evidence 集。单独运行查询 CLI 不算 Agent E2E。
