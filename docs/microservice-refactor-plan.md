# Go 后端微服务改造方案

> 状态：**方案已定稿，待开工（P0 未启动）**
> 日期：2026-10-05
> 范围：`backend/`（Go/Gin 单体）→ go-zero 微服务集群；`frontend/` 与 `agent/`（Python）契约不变

---

## 1. 背景与目标

### 1.1 为什么要拆

**第一驱动力是学习微服务架构**：以本项目真实业务（中药毒理知识平台 + 智能 Agent）为教材，完整实践微服务的核心模式（注册发现、gRPC、韧性、可观测性、消息驱动一致性、分库、容器编排）。

这不是一次由线上性能/故障/团队规模驱动的生产拆分。因此方案刻意选择"教学价值最大化"的路线（四个服务全拆、自写 Consul 适配、演练熔断），而不是"运维成本最小化"的路线。

### 1.2 目标

- 拆出 4 个业务微服务 + 1 个 API 网关，本地 `docker-compose` 一键拉起全套（含多副本）。
- 每个微服务核心模式都有真实落点和可验证产出（见第 9 章学习清单）。
- 拆分过程采用绞杀者模式，**每个阶段结束系统都完整可运行、可回滚**。

### 1.3 非目标（明确不做）

- ❌ 不改前端：所有现有 `/api` 路径由网关保持兼容，前端零改动。
- ❌ 不改 Python Agent 的对外/对内 HTTP 契约；它只通过环境变量切换 2 个回调地址。
- ❌ 不在本期上 K8s（留作 P7 选做）。
- ❌ 不更换语言/重写 Python Agent；不借拆分之名重写业务逻辑。
- ❌ 不为"不存在的规模问题"做过度设计（不引入服务网格、分布式事务框架等）。

---

## 2. 现状盘点

当前 Go 后端是一个**分层清晰、域间耦合很低**的 Gin 单体：handler → service → repository（GORM/gen）→ 单一 MySQL 库 `ai_medical_db`，Redis 做列表缓存与限流。

### 2.1 现有职责域

| 职责域 | 路由前缀 | 代码文件（handler/service/repository） | 运行时特征 |
|---|---|---|---|
| 身份与权限 | `/api/auth`、`/api/users` | user_*、middleware/auth | 短请求，JWT 签发 |
| 知识目录 CRUD | `/api/herbs`、`/decoctions`、`/couplets`、`/compounds`、`/papers`、`/cases`、`/clauses` | herb/decoction/couplet/compound/paper/expertise/imported_content | 短请求、读多写少、Redis 缓存 |
| Agent 编排 | `/api/agent/runs`、`/api/agent/sessions/*` | agent_run_*、agent_chat_*、client/agent | SSE 长连接、外部 HTTP 超时、幂等 |
| LLM 配置与代理 | `/api/admin/llm-config`、`/internal/v1/llm/chat(/stream)` | llm_config_*、llm_stream、util/crypto | 持有加密主密钥，转发 LLM 流式响应 |
| 内部知识检索 | `/internal/v1/knowledge/search` | knowledge_* | 供 Python Agent 回调 |

### 2.2 已有的跨进程基础（可直接复用）

Go 单体与 Python Agent 之间已经建立了成熟的服务间协作模式：

- `X-Agent-Token`：内部接口鉴权；
- `X-Trace-ID`：链路追踪透传；
- 超时/5xx 的状态收敛：Agent 调用结果不确定时立即 `GET` 回查或标记 `dispatch_unknown`；
- 创建侧幂等：`Idempotency-Key` 请求头 + Agent 侧 `run_id` 唯一约束。

这套约定平移到 Go 内部服务间调用与网关，不另起炉灶。

### 2.3 数据表现状（分库依据）

来源：`init_new_database.sql`、`migrations/`、`tmp/db.sql`。

**Go 单体当前使用的表：**

| 归属服务 | 表 |
|---|---|
| iam | `users` |
| knowledge | `herb_basic`、`herb_toxiccompound`、`herb_couplet_basic`、`herb_couplet_toxiccompound`、`decoction_basic`、`decoction_compound`、`decoction_toxiccompound`、`decoction_meta`、`molecular_info`、`papers`、`paper_tags`、`expertise`，以及 cases/clauses 对应的导入内容表（P4 核实具体表名） |
| agent（Go） | `agent_runs`、`agent_sessions`、`agent_chat_messages`、`agent_chat_turns` |
| llm-gateway | `llm_configs` |

**Python Agent 当前直接读写的表（`migrations/20260926_create_agent_mysql_storage.sql`）：**

- canonical 知识层 11 张：`knowledge_documents`、`knowledge_document_versions`、`knowledge_document_blocks`、`knowledge_document_chunks`、`knowledge_ingestion_jobs`、`knowledge_embedding_cache`、`knowledge_index_manifests`、`knowledge_legacy_evidence_mappings`、`knowledge_toxicology_snapshots`、`knowledge_toxicology_herbs`、`knowledge_toxicology_compounds`；
- Agent 运行态 3 张：`agent_workflow_runs`、`agent_chat_events`、`agent_tool_audits`。

### 2.4 关键耦合点（拆分难点）

1. **共享数据库**：所有表在同一 schema，服务代码好拆，数据边界要靠分库落实。
2. **Python Agent 直连 MySQL 读 canonical 知识层**：`knowledge_*` 表的物理 owner 将是 knowledge-svc，但 Python 现在绕过服务直接读库（见 6.5 的过渡策略）。
3. **SSE 长连接**：agent 聊天流需要穿过网关，gRPC 方案下用 server-streaming 承接。
4. **Redis 共用**：列表缓存 key（`herb:list:*` 等）与限流当前同实例，拆分后按服务分逻辑库（db index）或实例。

---

## 3. 目标架构

### 3.1 架构图

```
                        ┌──────────────────┐
  前端（零改动） ───────▶│  Gateway (BFF)   │  go-zero API：REST、JWT 验签、
                        │                  │  限流、路由聚合、SSE 透传
                        └────────┬─────────┘
                                 │ gRPC（zRPC，内网）
            ┌──────────┬─────────┼──────────┬────────────┐
            ▼          ▼         ▼          ▼            ▼
      ┌──────────┐┌──────────┐┌─────────┐┌──────────────┐
      │ iam-svc  ││knowledge ││agent-svc││llm-gateway   │
      │登录/用户 ││  -svc    ││runs/会话││密钥/LLM 代理 │
      │JWT 签发  ││CRUD/检索 ││SSE/幂等 ││              │
      └──────────┘└────┬─────┘└────┬────┘└──────▲───────┘
                       │ outbox    │ HTTP        │ HTTP 回调
                       ▼ + MQ      ▼             │
                 Meilisearch   Python Agent ─────┘
                 （索引同步）   （现有契约不变）

  基建：Consul（注册+健康检查+KV配置） / Jaeger（链路） /
        Prometheus + Grafana（指标） / RocketMQ（最终一致性） /
        MySQL（按服务分库） / Redis（按服务分逻辑库）
```

### 3.2 服务职责

| 服务 | 类型 | 职责 | 不做什么 |
|---|---|---|---|
| **gateway** | go-zero API | 对外 REST；JWT 验签；RBAC 入口校验；聚合下游 RPC；未迁移路由反代老单体；SSE ↔ gRPC stream 转换 | 不写业务逻辑、不直连业务库 |
| **iam-svc** | go-zero RPC | 登录/注册、用户管理、审批、JWT 签发；用户身份数据唯一来源 | 不做业务鉴权决策之外的事 |
| **knowledge-svc** | go-zero RPC | 全部目录 CRUD、canonical 知识层、内部检索接口、Meilisearch 索引同步、列表缓存 | 不感知 Agent 会话 |
| **agent-svc** | go-zero RPC | runs/sessions/turns 元数据、幂等、状态收敛、SSE 流编排、调用 Python Agent | 不直连 LLM；不读知识表（走检索接口） |
| **llm-gateway-svc** | go-zero RPC | `llm_configs` 与加密密钥保管、provider 路由、chat/stream 代理 | 不做业务 |

### 3.3 横切约定

- **身份透传**：网关验签后把 `user_id`、`role`、`tenant`（预留）放入 gRPC metadata，下游服务从 metadata 取，不再各自查用户。
- **内部鉴权**：服务间与 Python 回调沿用 `X-Agent-Token`（按服务发放不同 token，网关/服务侧统一拦截器校验）。
- **链路**：`X-Trace-ID` 与 OTel trace/span 打通，traceID 注入 Zap 日志字段。
- **错误码**：`common/errorx` 统一错误码区间与 gRPC status 映射，错误结构全服务一致。

---

## 4. 技术选型

| 维度 | 选型 | 决策理由 |
|---|---|---|
| 微服务框架 | **go-zero**（goctl 生成） | 工程全家桶：API/RPC 代码生成、自带熔断限流、Prometheus、OTel；logic 只写业务 |
| 网关 | **go-zero API 手写 BFF 聚合** | 灵活、SSE 好处理，能真正练习聚合层；不用 goctl gateway 自动转发 |
| 通信 | **内部 gRPC（zRPC）+ 对外 REST** | proto 作为契约单一来源；SSE 用 gRPC server-streaming |
| 注册/配置 | **Consul + 自写适配层** | 见 6.1；刻意自写以学习 gRPC naming/负载均衡原理 |
| 数据访问 | **保留 GORM / gen** | 降低迁移风险，精力集中在服务拆分；模型包按服务复制，不跨服务共享 |
| 数据库 | **MySQL 8.4，按服务分库** | `iam_db` / `knowledge_db` / `agent_db` / `llm_db` |
| 缓存 | Redis 7，按服务分 db index（0-1 网关/限流，2 knowledge，3 agent…） | 低成本逻辑隔离 |
| 消息队列 | RocketMQ 5 + outbox 本地消息表 | 可靠投递、消费幂等；knowledge→Meilisearch 为首个场景 |
| 搜索 | Meilisearch（现状不变） | 索引写入方从单体变为 knowledge-svc |
| 可观测 | go-zero 内置 Prometheus + OTel → Jaeger；Grafana 看板 | 不额外搭日志平台 |
| 部署 | docker-compose（多副本 + 依赖编排） | K8s 留作 P7 |

**被放弃的选项（备查）**：

- 注册中心改用 etcd：go-zero 原生零摩擦，但放弃 Consul 的学习目标 → 否决，坚持自写适配。
- 全 HTTP/JSON：最简单但练不到 gRPC/proto 主流栈 → 否决。
- goctl model + sqlx 替换 GORM：go-zero 正统范式，但 repository 全量重写会淹没拆分主线 → 本期否决，P6 后可作为对比练习。
- Kratos / 手写原生框架：学习更透但样板工作量翻倍 → 本期选 go-zero，手写原生体验通过 Consul 适配层补偿。

---

## 5. 目标目录结构（monorepo）

```
backend/
├── api/
│   ├── gateway/                # go-zero API 服务（BFF）
│   │   ├── gateway.api         # REST 契约（goctl api go 生成）
│   │   ├── etc/gateway.yaml
│   │   └── internal/{config,handler,logic,middleware,svc}
│   └── proto/                  # ★ 跨服务契约单一来源
│       ├── iam.proto
│       ├── knowledge.proto
│       ├── agent.proto
│       └── llmgateway.proto
├── rpc/
│   ├── iam/                    # 每个 RPC：goctl rpc protoc 生成
│   │   ├── etc/iam.yaml
│   │   └── internal/{config,logic,server,svc,model,repo}
│   ├── knowledge/
│   ├── agent/
│   └── llmgateway/
├── common/                     # 共享内核（只放技术设施，不放业务）
│   ├── consulx/                # 6.1 Consul 适配三件套
│   ├── errorx/                 # 错误码与 gRPC status 映射
│   ├── jwtx/                   # 签发/验签
│   ├── metadatax/              # user_id/role/trace 透传
│   ├── dbx/                    # GORM 初始化、gen 配置
│   └── logx/                   # Zap + traceID
├── cmd/                        # （过渡期）老单体入口，P6 删除
├── internal/                   # （过渡期）老单体代码，按阶段搬空
├── gen/                        # （过渡期）老 GORM gen 产物
└── deploy/
    ├── docker-compose.yml      # 全套环境与服务编排
    ├── consul/ jaeger/ prometheus/ grafana/ rocketmq/
    └── mysql/                  # 分库初始化 SQL
```

纪律：**proto 是跨服务 DTO 的唯一定义处**；RPC 服务之间不共享 model 包；`common/` 出现业务概念即视为越界。

---

## 6. 关键设计

### 6.1 Consul 适配层（common/consulx）——本期核心学习件

go-zero 的 zRPC 内置发现是 etcd，接 Consul 需要三个件：

1. **Registrar（服务端）**：服务启动时向 Consul Agent 注册 service（ID=`服务名-地址`，tags，meta，TTL check 或 HTTP check 指向 `/healthz`）；gRPC 服务端同时注册 `grpc_health_v1`；进程退出时 deregister，异常退出靠 TTL 过期摘除。
2. **Resolver（客户端）**：实现 gRPC `resolver.Builder`，scheme 注册为 `consul`；目标格式 `consul://agent-svc`。内部用 **Consul blocking query**（长轮询 + WaitIndex）watch 健康实例列表，地址变化时调用 `cc.UpdateState` 更新连接池；zRPC 内置 round-robin 即获得客户端负载均衡。
3. **配置引导**：客户端只配服务名，地址经 Consul 解析；Consul 地址本身来自启动 YAML/环境变量（唯一的静态配置）。

验收：起 2 个 agent-svc 副本，Consul UI 可见 2 实例；连续请求轮询命中两实例；kill 1 个后 blocking query 摘除、流量自动转移。

### 6.2 网关与认证

- 登录走网关 → iam-svc 签发 JWT；网关用 `.api` 的 `jwt:Auth` 对受保护路由统一验签。
- 公开读（herbs 等）保持 optional JWT（游客可读受限，与现状一致）。
- `AdminRequired` 由网关根据 claims 中 role 拦截，不进下游。
- gRPC metadata key 统一：`x-user-id`、`x-user-role`、`x-trace-id`。

### 6.3 SSE 透传

`GET /agent/sessions/:id/turns/:turn_id/stream`：

- 网关 handler 调 agent-svc 的 gRPC **server-streaming** RPC，收到消息即 flush 到 HTTP SSE，保持现有事件 JSON 格式；
- 正确处理客户端断连（ctx cancel 传播到 RPC）与网关写超时；
- Python Agent 侧仍由 Go 的 agent-svc 对接，Python 不感知 gRPC。

### 6.4 数据分库策略

- 同一 MySQL 实例建 4 个 schema，服务各持各的 DSN；**禁止跨库 join**，跨域数据通过 RPC 获取或冗余只读 id。
- agent-svc 表只保存 `user_id`，不保存用户昵称等（需要时调 iam，或 BFF 聚合）。
- 迁移 SQL 从 `init_new_database.sql` + `migrations/` 按表拆分到 `deploy/mysql/`，数据搬迁用 `CREATE TABLE ... LIKE` + `INSERT ... SELECT`，可重复执行、可回滚（保留原库直到 P6）。
- 过渡期老单体与新服务**共享旧库**（双读不双写：每迁一张表，写入口只有一个），切换顺序见第 7 章。

### 6.5 Python Agent 的直连库问题（重点风险）

- `knowledge_*`（11 张）归 knowledge-svc 所有；`agent_workflow_runs`/`agent_chat_events`/`agent_tool_audits` 为 Python 运行态自有表，物理上留在独立 schema（如 `agent_runtime_db`），Go 服务不碰。
- **过渡策略**：本期允许 Python Agent 使用**只读数据库账号**访问 `knowledge_db` 的 canonical 表（维持现状，避免改 Python 存储层）；其写入需求（ingestion 等）本期不变，沿用现状但记录在案。
- **目标状态（P7 之后）**：Python 对 canonical 表的访问逐步收口为 knowledge-svc 的内部 gRPC/HTTP API，最终实现"一个库一个写者"。本方案不在本期执行该收口，避免同时改两端。

### 6.6 消息驱动一致性（knowledge-svc）

场景：目录数据/毒理快照变更 → Meilisearch 索引更新。

- 业务表与 outbox 表在**同一本地事务**写入；
- relay 轮询/扫描 outbox 投递 RocketMQ，成功后标记（at-least-once）；
- 索引消费者幂等（按文档主键 upsert + 消息去重表/唯一键）；
- 验收：下单（写库）后 kill 消费者/丢消息，重启后索引最终一致；重复投递不产生脏数据。

### 6.7 可观测性与韧性

- 每个服务暴露 go-zero metrics（`/metrics`）与 `/healthz`；Prometheus 抓取，Grafana 看板覆盖 QPS/延迟/错误率/熔断状态。
- OTel 上报 Jaeger：一次"前端 → 网关 → agent-svc → Python"的请求能看到完整跨语言 trace。
- 韧性演练（P6）：停 Python Agent 观察 agent-svc 熔断与降级；限流阈值压测；Consul 摘实例演练。

---

## 7. 实施路线（绞杀者模式）

> 每个阶段：开工前明确验收；完成后系统可运行；任一阶段失败可回到上一阶段（老单体一直保留到 P6）。

### P0 准备与清点（约 0.5 天）

- 安装工具链：goctl、protoc/protoc-gen-go/protoc-gen-go-grpc、protoc 插件；确认 Docker 资源。
- 产出**路由 → 服务 → 表**最终归属表（本文档附录为初版），核实 cases/clauses 实际表名。
- 在 AGENTS.md 追加"微服务化进行中"说明与新目录约定。
- 验收：工具版本命令可跑；归属清单评审通过。**不动业务代码。**

### P1 基建骨架（约 2–4 天，学习核心）

- 建目录骨架与 `common/`；实现 consulx 三件套 + healthz。
- gateway 骨架（go-zero API）+ 一个 hello RPC 端到端：REST → 网关 → gRPC。
- compose 拉起 consul/jaeger/prometheus/grafana/rocketmq/mysql/redis/meilisearch。
- 验收：Consul UI 可见服务；2 副本轮询；kill 副本自动转移；Jaeger 有 trace；老单体照常运行。

### P2 iam-svc（约 1–2 天）

- `users` 迁 `iam_db`；登录/注册/用户管理 RPC + 网关路由；JWT 签发/验签就位。
- 网关开始**反代未迁移路径到老单体**（绞杀树干）。
- 验收：登录、用户管理、受保护接口全流程通过网关；老单体不再负责登录（由网关透传 claims 或老单体临时信任内部头，过渡后移除）。

### P3 llm-gateway-svc（约 1–2 天，最小业务服务）

- `llm_configs` 迁 `llm_db`；管理接口 + 2 个 internal chat 接口平移。
- Python Agent 的 LLM 回调 base URL 改指新服务（环境变量）。
- 验收：管理台保存配置、chat/stream（含流式）正常；Python 侧无代码改动。

### P4 knowledge-svc（约 3–5 天，最重）

- 12+ 张目录表迁 `knowledge_db`；7 组 CRUD 与 Redis 缓存迁移；内部知识检索接口承接 Python 回调（仅改 base URL）。
- 实现 outbox → RocketMQ → Meilisearch 同步全链路（6.6）。
- 验收：目录全部页面功能与缓存行为不变；索引最终一致演练通过；Python 检索回调正常。

### P5 agent-svc（约 2–3 天）

- 4 张 Go 侧 agent 表迁 `agent_db`；runs/sessions/turns 迁移；SSE 走 gRPC streaming（6.3）。
- 保留幂等键与 `dispatch_unknown` 收敛逻辑；Python 运行态 3 张表独立 schema 不动。
- 验收：Agent 工作区完整可用（发起、流式回复、断线重连/回查、resume、重复提交幂等）。

### P6 韧性演练与收官（约 1–2 天）

- 熔断/限流/摘除演练；Grafana 看板与告警规则；压测一轮。
- 删除老单体入口与 `internal/`、`gen/` 旧代码；compose 切换为唯一启动方式；更新 AGENTS.md。
- 验收：全量回归（前端走查 + 现有 Go 测试迁移后全绿 + Python 测试不受影响）；老代码清零。

### P7（选做，不在本期承诺）

同一套镜像上 K8s（Deployment/Service/ConfigMap/HPA）；Python canonical 表访问收口到 knowledge-svc API；可选 goctl model/sqlx 重写一个服务做对比。

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Consul 自写适配有 bug，发现不稳定 | 全服务调用受影响 | P1 先用 hello 服务充分验证（压测、摘除、重启）；保留 etcd 作为半天内可切换的兜底方案 |
| 分库后发现跨域 join 依赖 | 功能搬不过去 | P0 用 grep/EXPLAIN 核清所有跨表查询；跨域改 RPC 聚合或冗余 id，不允许"临时跨库查一把" |
| 绞杀期双写/写入口混乱 | 数据不一致 | 铁律：一张表同一时刻只有一个写者；切换以路由切走为界，老单体对应写接口立即下线 |
| Python 直连 knowledge 库 | 破坏库边界 | 6.5 过渡策略：只读账号 + 显式记录，目标收口列入 P7 之后 |
| SSE 经 gRPC 转换出现粘包/断流 | 聊天不可用 | P5 单独写流透传测试，保持现有事件 JSON 线格式不变，用前端现有 sse.ts 验证 |
| 学习项目过度工程化 | 拖成烂尾 | 以第 7 章阶段验收为准绳；每阶段只做清单内事项；不引入服务网格/分布式事务框架 |
| 本地资源不足（compose 全家桶） | 机器卡 | 基建组件可按需启停（如 RocketMQ 仅 P4 后常驻）；服务副本数用环境变量控制 |

---

## 9. 微服务模式学习清单（模式 → 落点 → 验收）

| # | 模式 | 练习落点 | 验收方式 |
|---|---|---|---|
| 1 | 领域边界 | 服务划分、proto 契约 | 无跨服务 model 依赖；proto 为 DTO 单一来源 |
| 2 | 注册发现 + 负载均衡 | consulx 三件套 | Consul UI、多副本轮询、摘除转移 |
| 3 | 配置外置 | Consul KV + 服务 YAML | 限流阈值热更新不重启（如时间不够降级为静态 YAML，热更新移 P6） |
| 4 | gRPC 生态 | proto、拦截器链、metadata、streaming | 全链路 gRPC；SSE 流式可用 |
| 5 | 认证授权 | JWT 签发/验签、claims 透传 | 网关统一鉴权，下游无用户查询 |
| 6 | 韧性 | go-zero 熔断/限流 + 超时传播 | 停 Python 演练、压测限流 |
| 7 | 可观测性 | OTel/Jaeger + Prometheus + traceID 日志 | 一条跨语言完整 trace；Grafana 看板 |
| 8 | 消息驱动一致性 | outbox + RocketMQ + 幂等消费 | kill 消费者后最终一致、重复投递不脏 |
| 9 | 数据边界 | 4 库分治、禁止跨库 join | 每库单写者；跨域走 RPC |
| 10 | 容器编排 | compose 多副本 + 依赖与健康检查 | 一键起全套，重启幂等 |

---

## 10. 待决问题（开工前/对应阶段关闭）

1. cases / clauses 对应的真实表名与数据源（P0 核实）。
2. Consul KV 配置热更新是否在 P1 做，还是 P3 之后补（默认后者）。
3. 过渡期老单体如何信任网关注入的身份头：共享内网 + 临时内部 token（P2 定）。
4. Python Agent 连接各 DB 的账号拆分与权限最小化（P4/P5 前在 compose 与 MySQL 授权中落实）。
5. 各服务端口规划（P0 在本文档附录补全：网关 8080，RPC 9xxx 段）。

---

## 附录 A：路由 → 服务归属初版

| 方法与路径 | 归属 | 备注 |
|---|---|---|
| POST `/api/auth/login`、`/api/auth/register` | iam | |
| GET/POST/PUT/DELETE `/api/users`、`PATCH /api/users/:id/status` | iam | admin |
| `/api/herbs` CRUD | knowledge | 公开读 + admin 写 |
| `/api/decoctions` CRUD | knowledge | 同上 |
| `/api/couplets` CRUD | knowledge | 同上 |
| `/api/compounds` CRUD | knowledge | 同上 |
| `/api/papers` CRUD | knowledge | 同上 |
| GET `/api/cases`、`/api/cases/:id` | knowledge | imported content |
| GET `/api/clauses`、`/api/clauses/:id` | knowledge | imported content |
| POST/GET `/api/agent/runs`、`POST /api/agent/runs/:run_id/resume` | agent | |
| `/api/agent/sessions/*`（含 turns stream） | agent | SSE |
| GET/PUT `/api/admin/llm-config` | llm-gateway | admin |
| POST `/internal/v1/llm/chat`、`/chat/stream` | llm-gateway | Python 回调 |
| POST `/internal/v1/knowledge/search` | knowledge | Python 回调 |
| `/swagger/*` | gateway（过渡期反代/聚合） | |

## 附录 B：端口规划（初稿，P0 定稿）

| 组件 | 端口 |
|---|---|
| gateway（REST） | 8080（对外） |
| iam-svc gRPC | 9001 |
| knowledge-svc gRPC | 9002 |
| agent-svc gRPC | 9003 |
| llm-gateway-svc gRPC | 9004 |
| Consul | 8500 |
| Jaeger UI / OTLP | 16686 / 4317 |
| Prometheus / Grafana | 9090 / 3001 |
| RocketMQ Dashboard | 8081 |
| MySQL / Redis / Meilisearch | 3306 / 6379 / 7700 |
