# API 文档与联调指引

本项目采用多层分布式架构，API 文档分布在不同的服务节点中。本指南旨在统一入口，说明调用关系与鉴权边界。

## 1. 架构与调用关系

系统分为三层主要逻辑架构：
1.  **前端 (React)**：用户交互层，通过代理调用 Go 后端接口。
2.  **后端 (Go Gateway)**：业务网关层。负责公共业务逻辑（CRUD）、用户鉴权（JWT）、流量控制，并作为 Python Agent 的安全代理。
3.  **智能体 (Python Agent)**：科研核心层。负责基于 LangGraph 的 ReAct 工作流、确定性科研 Skill 执行以及 RAG 向量检索。

**调用链路**: `前端 -> 后端 (Go) -> 智能体 (Python)`

## 2. API 文档入口

### 2.1 后端业务接口 (Go)
*   **交互地址**: `/swagger/index.html`
*   **生成命令**:
    ```bash
    cd backend && swag init -g cmd/server/main.go -o docs
    ```
*   **说明**: 包含用户管理、药材/方剂/对药/化合物/论文的 CRUD 接口，以及智能分析任务的外部触发入口。

### 2.2 智能体内部接口 (Python)
*   **交互地址**: `/docs` (Swagger UI) 或 `/redoc` (ReDoc)
*   **鉴权**: 内部接口受 `X-Agent-Token` 保护。
*   **说明**: 包含科研分析任务的实际执行接口（Internal V1）、Skill 注册信息及工具审计日志。

### 2.3 接口契约规范 (OpenAPI)
*   **路径**: `contracts/openapi/agent-internal-api.yaml`
*   **作用**: 作为后端与智能体服务间通信的**唯一事实来源 (SSOT)**。联调时，数据结构定义以此文件为准。

## 3. 鉴权边界

*   **外部鉴权 (User -> Go)**:
    *   使用 JWT 令牌。
    *   Header: `Authorization: Bearer <token>`
*   **内部鉴权 (Go -> Agent)**:
    *   使用预共享密钥。
    *   Header: `X-Agent-Token: <AGENT_INTERNAL_TOKEN>`
*   **链路追踪**:
    *   请求头包含 `X-Trace-ID`，用于跨服务日志聚合。

## 4. 异步处理流程与语义

### 4.1 Agent 运行 (Run) 流程
*   **创建**: `POST /internal/v1/runs` 启动长耗时分析，返回 `201 Created`。
*   **状态机**: `pending` -> `running` -> `completed` | `failed` | `cancelled`。
*   **结果获取**: `analysis_result` 和 `workflow` 详情仅在 `completed` 状态下完整返回。

### 4.2 对话回合 (Turn) 流程
*   **发起**: `POST /internal/v1/chat/turns` 返回 `202 Accepted`。
*   **事件流 (SSE)**: Go 后端提供 `/api/agent/sessions/:id/turns/:turn_id/stream` 接口。
*   **轮询语义**: 后端通过对 Agent 状态接口的轮询模拟流式输出。每个事件包含 `sequence` 序号，客户端需记录序号以支持断线重连后的幂等增量更新。

## 5. 业务限制与特殊边界

*   **动态内容 (Cases/Clauses)**: `cases` (病案) 与 `clauses` (条文) 接口返回 `Record<string, unknown>`。数据字段由外部 SQL 导入决定，不保证特定字段 Schema。
*   **能力状态**:
    *   **毒理活跃**: 系统当前主要处理毒理分析逻辑。
    *   **超分子下线**: `/evidence/search/diagnostics` 接口已禁用，返回 `supramolecular evidence is removed` 报错，仅用于维持旧版前端兼容性。
*   **RDKit 降级**: 若 Agent 未安装 `rdkit` 额外依赖，分子描述符将返回 `null`，且能力状态标记为 `degraded`。

---

### 契约一致性核查总结
1. **版本偏差**: 合约定义为 `0.8.0`，实际代码处于 `0.7.0` (Python) 和 `0.6.0` (Docker) 阶段。
2. **模型封装**: Go 后端在存储 `AnalysisResult` 时采用 `json.RawMessage` 透传，联调前端时应直接对照 Python 的 Pydantic 模型 Schema。


## 毒理词法检索：Elasticsearch 运维与回滚

Elasticsearch 是唯一词法检索后端；运行状态、聊天事件和 canonical knowledge 存放于 MySQL，LangGraph checkpoint 存放于 Redis Stack。启动 Elasticsearch：

```bash
docker compose --profile search up -d elasticsearch
```

Agent 关键环境变量如下：

```dotenv
AGENT_LEXICAL_BACKEND=elasticsearch
AGENT_ELASTICSEARCH_URL=http://elasticsearch:9200
AGENT_ELASTICSEARCH_INDEX_ALIAS=medical_toxicology_current
AGENT_ELASTICSEARCH_USERNAME=
AGENT_ELASTICSEARCH_PASSWORD=
AGENT_ELASTICSEARCH_TIMEOUT_SECONDS=3
AGENT_ELASTICSEARCH_VERIFY_CERTS=false
AGENT_ELASTICSEARCH_CA_CERTS=
```

默认构建 Elasticsearch 索引；需要 Qdrant 时必须显式包含 `qdrant`，并将 vector mode 设为 `optional` 或 `required`：

```bash
cd agent
uv run python -m app.scripts.build_toxicology_index \
  --targets elasticsearch,qdrant
```

上线前可执行不写入的检查；`--generation` 可用于固定版本名：

```bash
uv run python -m app.scripts.build_toxicology_index \
  --targets elasticsearch,qdrant --dry-run
```

构建过程先将结构化快照写入 MySQL，再创建版本化 ES 索引，逐项检查 bulk 结果并核对文档数和 reference ID，最后以单次 alias update 原子切换。Qdrant 继续独立建代并通过自己的 alias 发布；在线融合使用 RRF，不直接相加 BM25 与向量分数。

回滚通过将 `medical_toxicology_current` alias 原子切回上一代已验证索引完成。ES 不可用时不切换到其他词法实现，而是在 diagnostics/readiness 中明确报告降级；Qdrant 不可用时可保留 Elasticsearch 词法单路。

`GET /internal/v1/toxicology/retrieval/status` 返回 Elasticsearch 与 Qdrant 状态；原 `/evidence/search/diagnostics` 继续只表示已下线的超分子检索。
