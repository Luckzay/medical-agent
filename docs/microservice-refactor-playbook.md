# 微服务拆分实施手册（Playbook）

> 配套文档：[microservice-refactor-plan.md](./microservice-refactor-plan.md)（架构方案、边界、选型理由）
> 本文档只回答"每一步具体怎么做"：命令、骨架代码、验证点、回滚动作。
> 环境基准：macOS + Go 1.24 + Docker Desktop；日期：2026-10-05
> 状态：待开工（P0 未启动）

---

## 0. 使用规则（开工前必读）

1. **一次只推进一个任务**：当前任务的验收点全部通过后再勾选，禁止"批量标记完成"。
2. **静态 ≠ 运行**：`go build`/`go vet` 通过只算静态通过；必须实际发请求/看 UI/Consul UI/Jaeger 才算运行验收。
3. **每个任务有回滚**：老单体（`backend/cmd`、`backend/internal`、`backend/gen`）保留到 P6，任何一步出问题都能退回"纯单体可用"状态。
4. **提交粒度**：一个任务一个 commit，message 带阶段前缀，如 `P2(iam): 用户表迁移到 iam_db`。
5. **不扩散范围**：任务里没列的重构、换库、美化一律不做。
6. 命令中所有 `✏️` 标记处需要按实际值替换；带 ⚠️ 的步骤涉及数据/契约，执行前再读一遍。

### 总体时间线

| 阶段 | 产出 | 预估 |
|---|---|---|
| P0 | 工具链就绪、归属清单冻结 | 0.5 天 |
| P1 | 基建骨架 + hello 端到端 | 2–4 天 |
| P2 | iam-svc + 网关验签 | 1–2 天 |
| P3 | llm-gateway-svc | 1–2 天 |
| P4 | knowledge-svc + MQ 索引同步 | 3–5 天 |
| P5 | agent-svc + SSE 透传 | 2–3 天 |
| P6 | 韧性演练 + 老单体下线 | 1–2 天 |

---

## 1. P0 —— 准备与清点

### 1.1 安装工具链

```bash
# 1) goctl（go-zero 代码生成器）
go install github.com/zeromicro/go-zero/tools/goctl@latest

# 2) protoc 与插件（macOS，Apple Silicon）
brew install protobuf
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# 3) 验证（确认 $GOPATH/bin 在 PATH 中）
goctl --version          # 期望 goctl version 1.7.x 或更高
protoc --version         # 期望 libprotoc 25+
protoc-gen-go --version
protoc-gen-go-grpc --version
```

- [ ] 四个版本命令都有输出。记录版本号到本文档末尾"环境记录"。
- [ ] `docker compose version` 可用，Docker Desktop 运行中。

### 1.2 冻结"路由 → 服务 → 表"归属清单

方案文档附录 A 是初版。P0 需核实并关闭 5 个待决问题：

- [ ] cases/clauses 已核实：物理表名就是 **`cases`**、**`clauses`**，主键 `case_id`/`clause_id`，通过 [imported_content_repo.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/repository/imported_content_repo.go) 的白名单 map 动态访问；另有与 `herb_basic`/`decoction_basic` 的关联链接表（⚠️ 开工时读取该 repo 第 84–90 行确认链接表名，归入 knowledge）。
- [ ] 用 grep 核对所有跨表查询，登记到"跨域查询清单"（见 1.3）。
- [ ] 端口表定稿（默认采用方案附录 B：网关 8080，RPC 9001–9004）。
- [ ] 过渡期身份头方案定稿（见 4.3，默认：内网 + 共享内部 token）。
- [ ] Consul KV 热更新推后（P6 可选），P1 只用静态 YAML。

### 1.3 跨域查询盘点（分库前必须做）

```bash
cd backend
# 找出所有可能跨域的 join / 多表写法
grep -rn "Joins\|Table(" internal/repository/ > /tmp/cross_table.txt
```

- [ ] 逐条确认 join 的两表是否同一服务；跨域的登记为"RPC 聚合"或"BFF 拼装"，**禁止**留到分库后再发现。
- 已知跨域点：imported content 与 herbs/decoctions 的关联查询（同属 knowledge，库内 join 合法）。

### 1.4 建立分支与目录

```bash
git checkout -b feat/microservice
mkdir -p backend/api/gateway backend/api/proto backend/rpc backend/common backend/deploy
```

- [ ] 分支创建，空目录就位（可加 `.gitkeep`）。
- [ ] 在 [AGENTS.md](file:///Users/bytedance/Projects/medical-agent/AGENTS.md) 追加一节"微服务化进行中（P0 起）"：说明 `backend/api`、`backend/rpc`、`backend/common` 为新结构，`backend/internal` 为待搬空的老单体。

**P0 验收**：工具版本齐全；归属清单 + 跨域清单评审通过（自己通读一遍即可）；老单体 `go run ./cmd/server` 仍正常。
**回滚**：删除分支即可，无业务代码改动。

---

## 2. P1 —— 基建骨架（学习核心阶段）

> 目标：不碰业务，端到端打通"REST → 网关 → gRPC → Consul 发现 → trace"，后续业务只是复制模板。

### 2.1 拉起基建容器

- [ ] 新建 `backend/deploy/docker-compose.infra.yml`，包含：

| 服务 | 镜像（参考版本） | 端口 | 用途 |
|---|---|---|---|
| consul | `hashicorp/consul:1.20` agent -dev -client=0.0.0.0 | 8500 | 注册 + KV + UI |
| jaeger | `jaegertracing/all-in-one:1.62` | 16686(UI)/4317(OTLP) | 链路 |
| prometheus | `prom/prometheus:v2.55` | 9090 | 指标抓取 |
| grafana | `grafana/grafana:11.3` | 3001 | 看板 |
| rocketmq | 复用根 compose 的 mq profile | 9876/8081 | P4 才常驻 |

- [ ] 复用根目录 [docker-compose.yml](file:///Users/bytedance/Projects/medical-agent/docker-compose.yml) 已有的 mysql/redis/rocketmq/meilisearch（`profiles: ["mq"]` 已存在，P4 用 `--profile mq` 启动），不重复定义。
- [ ] Prometheus 抓取配置先放通配模板：job 名 `gozero-rpc`，抓取 Consul services 中带 `metrics=/metrics` tag 的实例（P1 先写静态 targets，Consul 服务发现抓取留到 P6）。

```bash
docker compose -f backend/deploy/docker-compose.infra.yml up -d consul jaeger
# 验收
open http://localhost:8500   # Consul UI
open http://localhost:16686  # Jaeger UI
```

- [ ] 两个 UI 可打开。

### 2.2 common 共享内核

按以下文件逐个创建，**只放技术设施**：

- [ ] `common/dbx/gorm.go`：从 [repository/db.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/repository/db.go) 抽出 GORM 初始化（入参 DSN，不做 AutoMigrate——模型归各服务）。
- [ ] `common/errorx/code.go`：错误码区间分配表（iam 1xxxxx / knowledge 2xxxxx / agent 3xxxxx / llm 4xxxxx / common 0xxxxx），`gRPC status ↔ 业务码` 映射函数。
- [ ] `common/jwtx/jwt.go`：把 [middleware/auth.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/middleware/auth.go#L16-L33) 的 `Claims`（user_id/username/role）与签发/验签逻辑搬入，HS256、24h 过期保持不变。
- [ ] `common/metadatax/keys.go`：常量 `x-user-id`、`x-user-role`、`x-trace-id`；提供从 gRPC metadata 读取/写入的 helper。
- [ ] `common/logx/zap.go`：Zap 初始化 + 从 context 提取 traceID 注入日志字段。

- [ ] `go build ./...` 通过。

### 2.3 Consul 适配三件套（本期核心学习件）⚠️

在 `common/consulx/` 下实现。**先写测试/验证程序，再接业务**。

**(a) Registrar（服务端）**

- [ ] `registrar.go`：服务启动时调用 Consul HTTP API `PUT /v1/agent/service/register`，字段：
  - `ID` = `<service-name>-<ip>-<port>`（保证多副本唯一）
  - `Name` = 服务名（如 `agent-rpc`，客户端 discovery 用它）
  - `Address/Port` = gRPC 监听地址
  - `Check`：TTL check（如 10s），起一个 goroutine 周期 `/v1/agent/check/pass/<checkId>` 心跳
  - `Tags`：`metrics=/metrics`（供 P6 Prometheus consul 抓取）
- [ ] gRPC 服务端注册标准健康探针：`google.golang.org/grpc/health` + `grpc_health_v1.RegisterHealthServer`。
- [ ] 进程退出时 deregister（`defer` + signal 处理）；异常退出靠 TTL 过期摘除。

**(b) Resolver（客户端）**

- [ ] `resolver.go`：实现 gRPC 的 `resolver.Builder`（`Build(target, cc, opts)` / `Scheme() string`），scheme 名为 `consul`，目标格式 `consul://agent-rpc`。
- [ ] `Build` 内起 goroutine 用 **Consul blocking query**（`GET /v1/health/service/<name>?passing&index=<X>&wait=30s`）长轮询健康实例；列表变化时调用 `cc.UpdateState(resolver.State{Addresses: ...})` 更新连接。
- [ ] 在包 `init()` 中 `resolver.Register(&consulBuilder{})`（或在客户端显式 `grpc.WithResolvers()`，二选一，文档化）。
- [ ] 地址使用 round-robin 负载均衡：dial option `grpc.WithDefaultServiceConfig(`{"loadBalancingPolicy":"round_robin"}`)`（策略名固定为 `round_robin`，勿拼错）。

**(c) 与 go-zero zRPC 的接线**（⚠️ 编码时以实际 goctl/go-zero 版本签名为准）

- [ ] 生成的 RPC client（`svc/servicecontext.go` 中 `zrpc.MustNewClient`）传入 `zrpc.WithDialOption(grpc.WithResolvers(consulx.Builder{}))`，target 用 `consul:///iam-rpc`，不使用 yaml 里的 `Etcd` 字段。
- [ ] 服务端在 main 启动流程中手动 `consulx.NewRegistrar(...).Register()`（不用 go-zero 内置的 `discov` etcd 注册）。

- [ ] **独立验收（不依赖业务）**：写一个 `cmd/consuldemo`：server 监听 9101/9102 两个实例并注册 `hello-rpc`；client 以 `consul:///hello-rpc` 连续发 20 个请求。
  - [ ] 静态：编译通过。
  - [ ] 运行：Consul UI 出现 2 个 `hello-rpc` 实例且均 passing。
  - [ ] 运行：20 次请求大致 10:10 落到两实例。
  - [ ] 运行：kill 一个实例 → 10s 内 Consul 摘除 → 后续请求全部命中存活实例，无报错。
  - [ ] 运行：重启实例 → 自动回到轮询。

### 2.4 创建 hello RPC 模板（goctl 全流程演练）

```bash
cd backend/api/proto
# 手写 hello.proto（package hello；service Hello { rpc Ping(PingReq) returns(PingResp) }）

# 生成 RPC 服务骨架（风格 go_zero，目录 rpc/hello）
goctl rpc protoc hello.proto \
  --go_out=../../rpc/hello --go-grpc_out=../../rpc/hello \
  --zrpc_out=../../rpc/hello -m
```

- [ ] 在生成的 `hello/internal/logic/pinglogic.go` 里返回服务端 hostname/IP。
- [ ] 在 `etc/hello.yaml` 只保留 `ListenOn`、`Mode`、`Telemetry`（不写 Etcd）。
- [ ] main.go 接入 consul registrar（2.3）+ health server。
- [ ] `go run hello.go -f etc/hello.yaml` 启动，Consul UI 可见。

### 2.5 创建 Gateway 骨架

```bash
cd backend/api/gateway
# 手写 gateway.api：一个 GET /api/ping（jwt:Auth 段先不加）
goctl api go -api gateway.api -dir . --style goZero
```

- [ ] ping logic 中用 zRPC client 调 `consul:///hello-rpc`（接 2.3 的 resolver dial option），返回下游地址。
- [ ] yaml 配置 `Telemetry`（Jaeger OTLP endpoint `localhost:4317`，采样率 1.0 便于学习期观察）。
- [ ] CORS 中间件从老单体平移（允许 origin、`Authorization`、`Idempotency-Key` 头）。

- [ ] **P1 总验收**：
  - [ ] `curl localhost:8080/api/ping` 返回下游实例地址；起两个 hello 副本时响应在两地址间轮换。
  - [ ] kill 一个副本，curl 不报错、自动转移。
  - [ ] Jaeger UI 中能看到 `gateway → hello` 的完整 span 链。
  - [ ] 老单体仍在 8080？⚠️ 端口冲突：P1 起网关占用 8080，老单体本地调试临时改 `SERVER_PORT=8081`；**P2 完成后老单体固定 8081 作为网关反代上游**。
- [ ] 在根 compose 或 infra compose 中固化端口约定。

**回滚**：`docker compose -f backend/deploy/docker-compose.infra.yml down`；删除 `backend/api`、`backend/rpc`、`backend/common`（本阶段无业务变更，老单体不受影响）。

---

## 3. 通用迁移动作（P2–P5 每阶段都要做，先读一遍）

每抽出一个服务，固定执行以下 8 个动作：

1. **建库**：`CREATE DATABASE <svc>_db CHARACTER SET utf8mb4;`（脚本放 `backend/deploy/mysql/NN_<svc>.sql`，幂等）。
2. **搬表**：`CREATE TABLE IF NOT EXISTS <svc>_db.t LIKE ai_medical_db.t;` + `INSERT ... SELECT ...`（数据搬迁脚本单独保存，可重复执行；切流前跑一次，切流窗口停老单体写入后再跑一次增量校验）。
3. **搬模型**：把相关 `internal/model/*.go` 复制到 `rpc/<svc>/internal/model/`，**改包名、不共享**；GORM/gen 用法保持。
4. **写 proto**：在 `api/proto/<svc>.proto` 定义 RPC 与消息（DTO 唯一来源），`goctl rpc protoc` 生成。
5. **迁 logic**：handler/service/repository 三层业务逻辑搬进 `<svc>/internal/logic`，repository 用本服务 DSN 的 dbx。
6. **网关接线**：`gateway.api` 增加对应 REST 路由（受保护段加 `jwt:Auth`），logic 调本服务 RPC；把该路径从"反代老单体"列表移除。
7. **配置与编排**：新增 `etc/<svc>.yaml`；compose 增加服务（含健康检查、Consul 注册所需环境变量、depends_on 基础设施三件套）。
8. **回归**：对应前端页面走查 + 老单体相关 `*_test.go` 迁移到 `rpc/<svc>/` 后 `go test ./...` 全绿。

切换铁律：**一张表同一时刻只有一个写者**。路由在网关切走的同一刻，老单体对应写路由注释/下线。

---

## 4. P2 —— iam-svc

### 4.1 数据搬迁

- [ ] `deploy/mysql/10_iam.sql`：创建 `iam_db`，搬 `users` 表（结构与数据）。
  - ⚠️ 验证：`SELECT COUNT(*) FROM iam_db.users` 与原库一致；保留原表到 P6。
- [ ] 给新服务建最小权限 MySQL 账号 `iam_svc@%`，只授 `iam_db.*`；老账号暂留。

### 4.2 RPC 实现

- [ ] `iam.proto`：`Login(LoginReq)->TokenResp`、`Register`、`ListUsers`、`CreateUser`、`UpdateUser`、`UpdateUserStatus`、`DeleteUser`；消息字段对齐现有 user_handler 的请求结构。
- [ ] 模型/逻辑来源：[user_service.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/service/user_service.go)、[user_handler.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/handler/user_handler.go)、[user_repo.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/repository/user_repo.go)。
- [ ] 签发逻辑使用 `common/jwtx`（claim：user_id/username/role，HS256，24h——与现网 token 完全一致，保证切流后已签发 token 不失效）。

### 4.3 网关与过渡期身份

- [ ] `gateway.api`：
  - `@handler login` / `register` 放公开段；
  - `/api/users` 整组放 `@server ( jwt: Auth )`，admin 校验在网关 logic 内按 claims.role 拦截（403 JSON 与现格式一致：`{"error":"需要管理员权限"}`）。
- [ ] 网关调 iam RPC 时不依赖 metadata；调其他业务 RPC 时把 claims 写入 metadata（`common/metadatax`）。
- [ ] **过渡期老单体信任链**（只在绞杀期存在，P6 删除）：网关反代老单体的请求注入内部头 `X-Internal-Auth: <共享密钥>` + `X-User-Id/Role`；老单体新增一个极简中间件：仅监听 127.0.0.1/内网且内部头正确时，用头信息建立 context，绕过 JWT 解析。
- [ ] 老单体固定 8081 启动（`SERVER_PORT=8081`），网关对未迁移路径反代 `http://host.docker.internal:8081`（本地）或 compose 服务名（容器化）。

### 4.4 验收与回滚

- [ ] 运行验收：登录拿到 token → 带 token 调一个仍在老单体的接口（如 `/api/herbs`）成功，证明网关验签 + 内部头透传 + 老单体信任链通。
- [ ] 运行验收：游客（无 token）访问公开读正常；伪造/过期 token 返回 401；非 admin 调 `/api/users` 返回 403。
- [ ] 运行验收：用户管理 5 个接口在前端"用户管理"页全部可用。
- [ ] P2 完成后路由分布：`/api/auth/*`、`/api/users/*` → iam；其余全部反代老单体。
- [ ] 回滚：网关路由表把 auth/users 改回反代老单体；iam_db 与 iam 服务停用即可，原库 users 表未删。

---

## 5. P3 —— llm-gateway-svc（最小业务服务，跑通服务间模式）

### 5.1 数据搬迁与 RPC

- [ ] `deploy/mysql/20_llm.sql`：建 `llm_db`，搬 `llm_configs`（⚠️ 表内有加密的 api_key；验证主密钥 `LLM_ENCRYPTION_KEY` 不变即可解密，见 [llm_config_service.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/service/llm_config_service.go) 与 [crypto.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/util/crypto.go)）。
- [ ] `llmgateway.proto`：`GetConfig`、`UpdateConfig`（admin）、`InternalChat`（一元）、`InternalChatStream`（**server-streaming**，消息块字段对齐现有流式协议）。
- [ ] 迁移 [llm_stream.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/service/llm_stream.go) 的流式转发逻辑到 streaming logic：逐块从上游 LLM 读取 → gRPC stream 发送；context 取消要正确传播到上游 HTTP 请求。

### 5.2 内部鉴权与 Python 切换

- [ ] `/internal/v1/llm/*` 挂在网关**公开端口但独立路径**，校验 `X-Agent-Token`（复用现有 token，不改 Python 侧值）。
- [ ] 管理接口 `/api/admin/llm-config` 走 jwt + admin。
- [ ] ⚠️ Python 侧只改环境变量（[docker-compose.yml](file:///Users/bytedance/Projects/medical-agent/docker-compose.yml#L141) 已有）：
  - `AGENT_LLM_PROXY_URL` → `http://host.docker.internal:8080/internal/v1/llm/chat`（指向网关，由网关路由到 llm 服务；stream 地址同理）。
  - Python 代码零改动。

### 5.3 验收与回滚

- [ ] 运行：前端 LLM 配置页读取/保存成功；用错误主密钥验证密文不可解密（确认密钥搬运无误）。
- [ ] 运行：在 Agent 工作区发起一次对话（或直接 curl stream 接口），流式输出连续无粘包/断流。
- [ ] 运行：错误/缺失 `X-Agent-Token` 返回 401。
- [ ] 回滚：环境变量改回 `:8081` 老单体地址（老单体的 llm 接口在 P6 前保留可运行）。

---

## 6. P4 —— knowledge-svc（最重阶段，含 MQ 一致性练习）

### 6.1 数据搬迁（分批，先结构后数据）

- [ ] `deploy/mysql/30_knowledge.sql`：建 `knowledge_db`，搬 13 张业务表：
  `herb_basic`、`herb_toxiccompound`、`herb_couplet_basic`、`herb_couplet_toxiccompound`、`decoction_basic`、`decoction_compound`、`decoction_toxiccompound`、`decoction_meta`、`molecular_info`、`papers`、`paper_tags`、`expertise`、`cases`、`clauses`（含 P0 核实出的关联链接表）。
- [ ] canonical 11 张 `knowledge_*` 表：物理归 `knowledge_db`，但 **Python Agent 继续使用其现有账号访问**——P4 先给 Python 账号授予 `knowledge_db` 中 11 张表的 **SELECT/现有 DML 权限**（维持现状，见方案 6.5），⚠️ 与"单写者"原则的例外在此显式登记，P7 后收口。
- [ ] 各表行数与原库逐一比对。

### 6.2 RPC 与缓存

- [ ] `knowledge.proto` 按 7 组资源定义 List/Detail/Create/Update/Delete + `InternalSearch`（供 Python 回调，字段对齐 [knowledge_service.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/service/knowledge_service.go)）。
- [ ] 迁移 7 组 handler/service/repo（herb/decoction/couplet/compound/paper/expertise/imported_content），逻辑照搬，不改业务行为。
- [ ] Redis 缓存：knowledge-svc 独占 db2；key 前缀沿用 `herb:list:*` 等；写操作失效缓存的逻辑保持。
- [ ] 游客受限逻辑（`public_access.go` 的 guest 条数限制等）平移到网关 + RPC：公开读 optional JWT，身份经 metadata 传入。
- [ ] Python 回调切换：`AGENT_KNOWLEDGE_API_URL` 指向网关 `/internal/v1/knowledge/search`（token 不变）。

### 6.3 outbox + RocketMQ + Meilisearch 索引同步（核心练习）⚠️

- [ ] 在 `knowledge_db` 建 `index_outbox(id, agg_type, agg_id, payload JSON, status[pending/sent], retry_count, created_at, sent_at)`，与业务写入在**同一 GORM 事务**内创建 pending 记录。
- [ ] relay 协程（knowledge-svc 内）：扫描 pending → 投递 RocketMQ（topic `knowledge-index`）→ 标记 sent；失败重试退避；启动 `--profile mq` 的 rocketmq 容器。
  - Go 客户端选型：RocketMQ 5.3.2 开了 proxy（8081），用 `github.com/apache/rocketmq-clients-go/v5`；⚠️ P4 编码时跑通最小 produce/consume demo 再写业务。
- [ ] 消费者（同服务独立 consumer group 即可，学习期单进程）：收到消息 → 按 agg_type 重建 Meilisearch 文档并 **primary key upsert**（天然幂等）；消费端再用 outbox id 去重表兜底。
- [ ] 一致性演练（必做，运行验收）：
  - [ ] 新增/修改一味药 → 索引在数秒内更新，搜索可命中。
  - [ ] 消费到一半 kill 服务 → 重启后 pending/outbox 重投，索引最终一致。
  - [ ] 手动重复投递同一条消息 → 索引结果无重复、无脏数据。

### 6.4 验收与回滚

- [ ] 前端全部目录页面（列表/详情/搜索/分页/管理端增删改）走查通过。
- [ ] 游客读限制、管理员写权限与现状一致。
- [ ] Python Agent 发起一次任务，知识检索回调正常（任务证据可命中）。
- [ ] 老单体中 knowledge 相关写路由在网关切走后立即注释下线（读路由可保留到本阶段结束再删）。
- [ ] 回滚：网关 knowledge 路径整组改回反代；MQ 消费者停用，数据无破坏（outbox 只是旁路）。

---

## 7. P5 —— agent-svc（SSE 与状态收敛）

### 7.1 数据搬迁

- [ ] `deploy/mysql/40_agent.sql`：建 `agent_db`，搬 Go 侧 4 表：`agent_runs`、`agent_sessions`、`agent_chat_messages`、`agent_chat_turns`（历史列变更见 migrations，逐列比对，⚠️ 尤其 `message`、`history_json`、`next_event_sequence`、`error_message` 允许 NULL 的现状）。
- [ ] Python 运行态 3 表（`agent_workflow_runs`、`agent_chat_events`、`agent_tool_audits`）留在 `ai_medical_db` 不动（Python 独占），Go 服务不连。

### 7.2 RPC 与 SSE 透传

- [ ] `agent.proto`：CreateRun/GetRun/ResumeRun/CreateSession/ListSessions/GetSession/SendMessage/GetTurn（一元）；`StreamTurn(StreamReq) returns stream StreamEvent`。
- [ ] 迁移 [agent_run_service.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/service/agent_run_service.go) 与 [agent_chat_service.go](file:///Users/bytedance/Projects/medical-agent/backend/internal/service/agent_chat_service.go)：
  - [ ] `Idempotency-Key` 幂等、request hash 去重逻辑原样保留；
  - [ ] 对 Python Agent 的超时/5xx 处理保留：不确定立即 GET 回查或标记 `dispatch_unknown`；
  - [ ] HTTP client 迁为 `common` 下统一 client 包（baseURL/timeout/`X-Agent-Token`/`X-Trace-ID` 注入集中封装）。
- [ ] 网关 SSE handler：调用 gRPC stream → 逐条 flush 为现有 SSE 事件 JSON（**线格式不变**，前端 [sse.ts](file:///Users/bytedance/Projects/medical-agent/frontend/src/utils/sse.ts) 零改动）；客户端断连时 ctx cancel 传播。

### 7.3 验收与回滚

- [ ] Agent 工作区：新建会话、发消息、流式回复、历史 turns 回查、断线重连、resume、重复提交（同 Idempotency-Key 不产生重复 run）。
- [ ] 停掉 Python Agent 后发起对话：行为与现状一致（错误/收敛状态正确），且不影响网关与其他服务。
- [ ] Jaeger 中可见 `前端 → 网关 → agent-svc → Python`（跨语言 OTel，⚠️ Python 侧 trace 透传若未接，至少 Go 段完整、traceID 经 `X-Trace-ID` 关联）。
- [ ] 回滚：agent 路径改回反代老单体。

---

## 8. P6 —— 韧性演练、观测收官、老单体下线

### 8.1 韧性演练（每项都要实际操作并记录现象）

- [ ] 熔断：停 Python Agent，连续发对话请求，观察 go-zero 自适应熔断（错误率/快速失败）；恢复后自动半开探测。
- [ ] 摘除：agent-svc 双副本，kill 其一，Consul 摘除、流量转移无错误。
- [ ] 限流：对网关/接口施压验证限流阈值与 429 响应。
- [ ] 超时传播：给 knowledge RPC 配置 deadline，制造慢查询，确认上游不会无限等待。

### 8.2 观测收口

- [ ] 各服务 `/metrics` 被 Prometheus 抓取（改用 Consul 服务发现抓取或静态 targets 全覆盖）。
- [ ] Grafana 建一个看板：各服务 QPS、p95/p99 延迟、错误率、CPU/内存、熔断状态。
- [ ] 关键告警规则（学习项目可只写规则不接通知）：服务健康实例=0、错误率 >10%、p99 >2s。

### 8.3 老单体下线 ⚠️（不可逆动作，选一个维护窗口）

- [ ] 前置：P2–P5 全部回归通过；各库行数比对完成；老单体连续 1 周不承接生产流量（仅本地备用）。
- [ ] 删除 `backend/cmd`、`backend/internal`、`backend/gen`；移除网关反代上游与临时内部头信任中间件。
- [ ] compose 定稿：网关 + 4 RPC（agent/knowledge 双副本起步）+ 基建；`docker compose up -d` 一键起全套。
- [ ] 更新 [AGENTS.md](file:///Users/bytedance/Projects/medical-agent/AGENTS.md) 技术栈与目录章节；更新根 README 的启动命令。
- [ ] 原 `ai_medical_db` 保留备份后再考虑清理；MySQL 账号最小化（每服务只授自己库）。
- [ ] 全量回归：前端走查 + `go test ./...`（全部新目录）+ `agent/tests`（Python）不受影响。

---

## 9. 附录

### 9.1 goctl 命令速查

```bash
# RPC（在 backend/api/proto 下执行，-m 表示 proto 内多 service/同目录生成）
goctl rpc protoc <svc>.proto \
  --go_out=../../rpc/<svc> --go-grpc_out=../../rpc/<svc> \
  --zrpc_out=../../rpc/<svc> -m

# API（在 backend/api/gateway 下执行；改 .api 后重复执行可增量生成）
goctl api go -api gateway.api -dir . --style goZero

# proto 修改后重新生成（goctl 会保留 logic 文件，仅刷新骨架）
```

### 9.2 服务 YAML 最小模板（RPC）

```yaml
Name: iam-rpc
ListenOn: 0.0.0.0:9001
Mode: dev
# 不写 Etcd：发现由 common/consulx 承担
Consul:
  Host: 127.0.0.1:8500
  Service: iam-rpc
  TTLSeconds: 10
DataSource: iam_svc:✏️密码@tcp(mysql:3306)/iam_db?charset=utf8mb4&parseTime=true&loc=Asia%2FShanghai
Redis:
  Addr: redis:6379
  Type: node
  DB: 2
Telemetry:
  Name: iam-rpc
  Endpoint: jaeger:4317
  Sampler: 1.0
  Batcher: grpc
```

### 9.3 数据库分库与账号总表

| 库 | 表 | 服务账号 | Redis db |
|---|---|---|---|
| `iam_db` | users | iam_svc | — |
| `knowledge_db` | 13+ 目录表、11 张 knowledge_*、index_outbox | knowledge_svc（Python 账号对 11 张 canonical 表保留现权，例外登记） | 2 |
| `agent_db` | agent_runs/agent_sessions/agent_chat_messages/agent_chat_turns | agent_svc | 3 |
| `llm_db` | llm_configs | llm_svc | — |
| `ai_medical_db`（暂留） | Python 运行态 3 表；P6 后改名 `agent_runtime_db` | 仅 Python | 0 不变 |

### 9.4 已登记的风险与坑（执行中持续补充）

- go-zero 内置发现是 etcd：**不要**在 yaml 配 Etcd，注册/发现全走 `common/consulx`，避免双注册。
- 网关 8080 与老单体冲突：P1 起老单体本地用 8081，P2 起固定为反代上游。
- `llm_configs` 密文：换库不换 `LLM_ENCRYPTION_KEY`，否则全部 api_key 解不开。
- gRPC round-robin 策略 JSON 拼写为 `round_robin`；需要每个子连接就绪（block/health ready 策略按需加 `grpc.WithDefaultServiceConfig`）。
- Consul blocking query 必须带上一轮的 `X-Consul-Index`，并处理 419/索引回退。
- SSE 透传注意 HTTP handler 的 `Flusher` 缓冲与 gRPC stream 收发改用同一 ctx。
- Go 1.24 下安装 goctl/插件后如遇 `GOTOOLCHAIN` 自动下载，设 `GOTOOLCHAIN=local`（与本机 Go 版本一致时）。

### 9.5 环境记录（P0 填写）

| 工具 | 版本 |
|---|---|
| go | |
| goctl | |
| protoc | |
| protoc-gen-go | |
| protoc-gen-go-grpc | |
| Docker Desktop | |
| go-zero（go.mod） | |

### 9.6 阶段验收总清单（收官前逐项打勾）

- [ ] P1：Consul 注册/摘除/轮询/Jaeger trace 全部运行验证通过
- [ ] P2：登录与用户管理走查通过；过渡信任链仅内网可达
- [ ] P3：配置密文可解密；LLM 流式连续；Python 零代码改动
- [ ] P4：全部目录功能回归；MQ 最终一致 + 幂等演练通过
- [ ] P5：Agent 全功能 + 幂等 + 状态收敛；SSE 线格式未变
- [ ] P6：四项韧性演练留记录；Grafana 看板可用；老单体代码清零；compose 一键起全套
