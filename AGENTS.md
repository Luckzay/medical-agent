# AI Medical Agent — 项目约定与技术手册

> 本文件是 AI 编程助手（Codex、Cursor、Copilot 等）的项目上下文说明书。
> 修改技术选型或开发规范时，请同步更新此文件。

---

## 项目概述

中医药知识库全栈应用，分两阶段建设：

- **Phase 1**：CRUD Web 应用——方剂、单味药、对药、论文、分子信息、名家经验的浏览与管理
- **Phase 2**：智能 Agent——基于 LLM/RAG 的语义检索、用药分析、毒性报告自动生成

---

## 技术栈

| 层 | 选型 | 备注 |
|---|---|---|
| 前端 | React 18 + Vite + TypeScript | UI 库 Ant Design 5 |
| 后端 API | Go 1.22+ + Gin | 高并发 CRUD 层 |
| ORM | GORM Gen | 从数据库反向生成类型安全代码 |
| Agent（Phase 2） | Python 3.12+ + FastAPI | LangChain / LlamaIndex |
| 数据库 | MySQL 8.4 | utf8mb4, InnoDB |
| 缓存 | Redis 7 | go-redis/v9 |
| 消息队列 | RocketMQ 5 | 异步任务与事件流 |
| 搜索引擎 | Meilisearch | 中文全文检索 |
| 配置管理 | Viper | .env + config.yaml |
| 日志 | Zap | 高并发零分配 |
| 鉴权 | JWT | golang-jwt/v5，users 表 bcrypt |
| API 文档 | Swaggo | 注释自动生成 Swagger |
| 反向代理 | Nginx | 生产环境统一入口 |
| 部署 | Docker Compose | 所有服务容器化 |

---

## 项目目录结构

```
medicalagent/
├── AGENTS.md                  # 本文件——AI 助手的项目说明书
├── .agents/                   # Codex Agent 配置（敏感信息）
│   └── secret.md              # 数据库密码等凭证（不入 git）
├── .env.example               # 环境变量模板
├── docker-compose.yml         # 本地开发环境
│
├── backend/                   # Go API 服务
│   ├── cmd/
│   │   └── server/
│   │       └── main.go        # 入口
│   ├── internal/
│   │   ├── handler/           # Gin 路由 + 请求处理
│   │   ├── service/           # 业务逻辑
│   │   ├── repository/        # 数据访问（GORM Gen 调用层）
│   │   ├── model/             # GORM 模型定义
│   │   ├── middleware/        # JWT、CORS、日志等中间件
│   │   └── config/            # Viper 配置加载
│   ├── gen/                   # GORM Gen 自动生成代码（勿手动编辑）
│   ├── migrations/            # 数据库迁移脚本
│   ├── go.mod
│   └── go.sum
│
├── frontend/                  # React SPA
│   ├── src/
│   │   ├── pages/             # 页面组件
│   │   ├── components/        # 通用组件
│   │   ├── services/          # API 调用封装
│   │   ├── hooks/             # 自定义 hooks
│   │   ├── types/             # TypeScript 类型定义
│   │   └── utils/             # 工具函数
│   ├── vite.config.ts
│   └── package.json
│
├── agent/                     # Python Agent 服务（Phase 2）
│   ├── app/
│   │   ├── api/               # FastAPI 路由
│   │   ├── core/              # LLM/RAG 核心逻辑
│   │   └── models/            # Pydantic 模型
│   ├── requirements.txt
│   └── pyproject.toml
│
├── init_new_database.sql      # 数据库初始化脚本（schema 单一事实来源）
└── ai_medical_db_backup.sql   # 旧库备份
```

---

## 开发规范

### Go 后端

- **ORM 工作流**：修改 `init_new_database.sql` 后，运行 `gorm gen` 重新生成 `gen/` 目录代码
- **不使用裸 SQL 字符串拼接**：repository 层通过 GORM Gen 生成的 query API 操作数据库
- **错误处理**：不吞错误，每层 return error 向上传递，handler 层统一处理并返回 HTTP 状态码
- **配置**：敏感信息（数据库密码、JWT secret、RocketMQ 地址）走环境变量或 `.env`，不入 git
- **日志**：用 Zap 的 `zap.L()` 全局 logger，不 `fmt.Println`
- **API 风格**：RESTful，JSON 请求/响应，路由文件按资源拆分

### 前端

- **组件拆分**：页面组件 (`pages/`) 只负责布局和状态，通用 UI 放 `components/`
- **类型安全**：禁止 `any`，API 返回值必须有对应 TypeScript interface
- **状态管理**：初期用 React Context + hooks，不引入重型状态库
- **API 调用**：统一封装在 `services/` 层，不直接在组件里 fetch

### 通用

- **命名**：
  - Go：驼峰（公开 PascalCase，私有 camelCase）
  - 数据库字段：snake_case（保持现有风格）
  - 前端文件：PascalCase 组件，camelCase 工具/hooks
- **git commit**：中文或无妨，但尽量描述清楚改动内容
- **文件编码**：全部 UTF-8

---

## 数据库连接信息

MySQL 连接串格式：

```
user:password@tcp(host:port)/ai_medical_db?charset=utf8mb4&parseTime=true&loc=Asia%2FShanghai
```

开发环境默认值：

```
host: 127.0.0.1
port: 3306
user: root
database: ai_medical_db
```

⚠️ **密码等敏感信息存放于 `.agents/secret.md` 或 `.env`，不写在本文件中。**

GORM Gen 连接配置示例（`backend/cmd/generator/main.go`）：

```go
import "gorm.io/gen"

func main() {
    g := gen.NewGenerator(gen.Config{
        OutPath: "../gen",
        Mode:    gen.WithDefaultQuery,
    })
    // 从 .env 读取 DSN，不硬编码
    db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{})
    g.UseDB(db)
    g.GenerateAllTable()
    g.Execute()
}
```

---

## 常用命令

```bash
# 开发环境一键启动
docker-compose up -d

# Go 后端
cd backend
go mod tidy
go run ./cmd/server        # 启动 API 服务
gorm gen                   # 从数据库重新生成模型代码

# 前端
cd frontend
npm install
npm run dev                # Vite 开发服务器

# 数据库
mysql -u root -p ai_medical_db < init_new_database.sql
```

---

## 页面设计规范

详见 `.agents/design.md`。黑白极简风格，白色背景 + 近黑色文字 + 浅灰边框，PC/移动端双端适配。

---

## 架构要点

1. **Go 做 API，Python 做 Agent**：不在同一个进程里混用。Go 通过 HTTP/gRPC 调用 Python Agent 服务
2. **RocketMQ 用于异步任务**：论文批量导入、Meta 分析重算、毒性报告生成等耗时操作投递到 RocketMQ；MVP 阶段 Agent Run 继续使用可靠的 HTTP 调度，后续迁移为生产者/消费者模式
3. **Meilisearch 做搜索层**：方剂、单味药、论文写入 MySQL 后同步索引到 Meilisearch，中文分词无需额外配置
4. **Phase 2 不改变 Phase 1 架构**：Agent 服务和 API 服务独立部署，Nginx 统一路由
