# 中药毒理与循证数据库平台

## 启动方式

### 1. 数据库

确保 MySQL 8.4 已启动，执行建库脚本：

```bash
mysql -u root -p < init_new_database.sql
```

如果已有旧库数据，按 `init_new_database.sql` 文件头部的三步说明迁移。

### 2. 后端

```bash
cd backend
cp ../.env.example .env          # 编辑 .env 填入数据库密码和 JWT_SECRET
go mod tidy
go run ./cmd/server              # 默认监听 :8080
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev                      # 默认监听 :3000，API 请求自动代理到 :8080
```
# 找到占用 3000 端口的进程 PID
netstat -ano | findstr :3000
# 记下最后的 PID 数字，然后：
taskkill /PID <PID> /F
---

## 中间件使用情况

当前项目处于 Phase 1（CRUD Web 应用），仅使用了 **MySQL** 作为数据库，通过 GORM 连接。以下组件**暂未使用**：

| 组件 | 状态 | 说明 |
|---|---|---|
| MySQL | 已使用 | GORM 驱动，config.go 中 DSN 连接 |
| Redis | 未使用 | 配置结构已定义，无实际初始化或调用 |
| Kafka | 未使用 | 配置结构已定义，无实际初始化或调用 |
| Meilisearch | 未使用 | 未接入，中文全文检索待 Phase 2 |
| Nginx | 未使用 | 生产环境统一入口，本地开发不需要 |

Redis 和 Kafka 的配置已在 `config.go` 中预留，`go.mod` 不含对应依赖包，待 Phase 2 引入。
