# 中药毒理与循证数据库平台

## macOS / Linux 本地调试

### 1. 环境要求

| 工具 | 建议版本 | 用途 |
|---|---:|---|
| Go | 1.24+ | 运行主后端 |
| Python | 3.12 | 运行 Agent 服务 |
| Conda 或 uv | 最新稳定版 | Python 环境与依赖管理；推荐使用 Conda 管理本地环境 |
| Node.js | 18+ | 运行 React 前端 |
| MySQL | 8.4 | 业务数据和 Agent Run 状态 |
| Redis | 7+ | 缓存；后续用于工作流 Checkpoint |
| Docker Desktop / Docker Engine | 可选 | 快速启动基础设施和 Agent 容器 |

macOS 可以使用 Homebrew 安装主要依赖：

```bash
brew install go python@3.12 uv node mysql redis
```

Linux 安装方式因发行版而异。安装 Python 3.12 后，可以使用官方安装脚本安装 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

确认环境：

```bash
go version
python3.12 --version
uv --version
node --version
npm --version
mysql --version
redis-cli --version
```

### 2. 获取代码并准备配置

```bash
cd /Users/bytedance/Projects/medical-agent   # macOS 示例
# cd ~/projects/medical-agent                # Linux 示例

cp .env.example backend/.env
cp agent/.env.example agent/.env
```

生成一个本地内部服务密钥：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

把输出的同一个密钥分别填入：

```text
backend/.env: AGENT_INTERNAL_TOKEN=生成的密钥
agent/.env:   AGENT_INTERNAL_TOKEN=生成的密钥
agent/.env:   AGENT_OFFLINE_MODE=true
agent/.env:   AGENT_WORKER_COUNT=2
```

`AGENT_OFFLINE_MODE=true` 是默认且可复现的本地模式，只读取内置种子数据。设置 `AGENT_OFFLINE_MODE=false` 后，服务会用已知候选成分名向 PubChem 补全 CID/SMILES，并用 `AGENT_PUBCHEM_TIMEOUT_SECONDS=2.0` 控制超时；网络失败不会中断本地分析。未知药材名不会被直接当作化合物查询。

同时在 `backend/.env` 中填写 MySQL 密码和 JWT 密钥：

```dotenv
DB_USER=root
DB_PASSWORD=你的本地MySQL密码
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=ai_medical_db

JWT_SECRET=请替换为随机长字符串

AGENT_SERVICE_URL=http://127.0.0.1:8090
AGENT_SERVICE_TIMEOUT_SECONDS=10
AGENT_INTERNAL_TOKEN=与agent/.env相同的密钥
```

不要提交 `backend/.env`、`agent/.env` 或任何真实密钥。

### 3. 启动 MySQL 与 Redis

#### 方式 A：使用 Docker

先在当前终端设置 Compose 所需的内部密钥：

```bash
export AGENT_INTERNAL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

如果使用此方式生成密钥，请把 `$AGENT_INTERNAL_TOKEN` 的值同时写入 `backend/.env` 和 `agent/.env`。

启动基础设施：

```bash
docker compose up -d mysql redis meilisearch

docker compose ps
```

#### 方式 B：使用本机服务

macOS：

```bash
brew services start mysql
brew services start redis
```

Linux（服务名可能因发行版而异）：

```bash
sudo systemctl start mysql
sudo systemctl start redis-server
```

验证：

```bash
mysqladmin ping -h 127.0.0.1 -u root -p
redis-cli ping
```

### 4. 初始化数据库

在项目根目录运行：

```bash
mysql -u root -p < init_new_database.sql
```

如果已有旧库数据，请按 `init_new_database.sql` 文件头部说明迁移。Agent Run 表会在 Go 后端启动时通过 GORM AutoMigrate 自动补齐，也可以按顺序显式执行：

```bash
mysql -u root -p ai_medical_db < migrations/20260808_create_agent_runs.sql
mysql -u root -p ai_medical_db < migrations/20260808_add_agent_analysis_result.sql
mysql -u root -p ai_medical_db < migrations/20260808_add_agent_run_workflow.sql
```

### 5. 启动 Python Agent

打开第一个终端。推荐使用 Conda：

```bash
conda create -n medical-agent python=3.12 pip -y
conda activate medical-agent
cd agent
python -m pip install --upgrade pip
python -m pip install -e ".[rdkit]"
uvicorn app.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8090
```

如果暂时不安装 RDKit，可改为 `python -m pip install -e .`。服务仍能运行，但分子描述符为 `null`，`analysis_result.capabilities.rdkit.status` 会明确返回 `degraded`。

也可以使用 uv：

```bash
cd agent
uv sync --dev --extra rdkit --extra embedding
uv run uvicorn app.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8090
```

生产环境或 Windows 发布包使用锁定依赖安装，必须同时启用 `rdkit` 和 `embedding`：

```bash
uv sync --python 3.12 --frozen --no-dev --extra rdkit --extra embedding
```

`embedding` extra 会安装 `sentence-transformers`。缺少该 extra 时，`build_production_index` 会在生成向量阶段报 `ModuleNotFoundError`。

验证健康检查：

```bash
curl http://127.0.0.1:8090/health
```

可交互 API 文档：

```text
http://127.0.0.1:8090/docs
```

内部接口需要携带 `X-Agent-Token`。可以直接验证最小 Agent Run：

```bash
TOKEN="这里填写agent/.env中的AGENT_INTERNAL_TOKEN"

curl -X POST http://127.0.0.1:8090/internal/v1/runs \
  -H "Content-Type: application/json" \
  -H "X-Agent-Token: ${TOKEN}" \
  -d '{
    "run_id": "run-local-demo-001",
    "user_id": 1,
    "trace_id": "trace-local-demo-001",
    "herbs": ["甘草", "黄芪", "当归"],
    "research_goal": "分析药材毒理属性"
  }' | python -m json.tool
```

Iteration 4 将任务执行改为持久化异步模式。创建接口先把任务写入 SQLite，再立即返回 `status=running`；后台线程依次执行 `normalize → finalize`。Go 查询运行中任务时会向 Python Agent 对账，并在完成后把 `analysis_result` 和 `workflow` 保存到 MySQL。

LangGraph Checkpoint 使用独立的 SQLite 数据库，`run_id` 仍作为 `thread_id`。Python Agent 重启后会扫描持久化的 `running` 任务：已有 Checkpoint 的任务从断点继续，没有 Checkpoint 的任务从原始输入重新开始。Docker Compose 使用 `agent_data` 数据卷保存两个 SQLite 文件。

可以轮询查询结果：

```bash
curl http://127.0.0.1:8090/internal/v1/runs/run-local-demo-001 \
  -H "X-Agent-Token: ${TOKEN}" | python -m json.tool
```

最终结果仍包含标准化药名、成分与 SMILES、RDKit 描述符、逐条规则评分、能力降级状态、证据引用和节点执行轨迹。内置离线种子数据当前覆盖甘草、黄芪和当归；其他名称在离线模式下会进入 `summary.unresolved_herbs`。

### 5.1 Skill Registry 与 MCP 工具

Iteration 5 将确定性科研能力注册为版本化工具，例如 `normalize_herbs`。LangGraph 与 MCP 共用同一 Tool Runtime，不存在两套科研算法。

当前注册了毒理相关的科研 Skill。可以通过内部接口查看工具 Schema、权限、超时、重试策略及 Skill 绑定关系：

```bash
curl http://127.0.0.1:8090/internal/v1/tools \
  -H "X-Agent-Token: ${TOKEN}" | python -m json.tool

curl http://127.0.0.1:8090/internal/v1/skills \
  -H "X-Agent-Token: ${TOKEN}" | python -m json.tool

curl http://127.0.0.1:8090/internal/v1/runs/run-local-demo-001/tool-audits \
  -H "X-Agent-Token: ${TOKEN}" | python -m json.tool
```

每次工具调用都会记录工具版本、节点、耗时、状态、尝试次数和错误类型，但不会记录 Token 或完整输入。MCP 使用官方 Python SDK 的无状态 Streamable HTTP 传输：

```text
URL: http://127.0.0.1:8090/mcp/
Header: X-Agent-Token: <AGENT_INTERNAL_TOKEN>
```

MCP 客户端可以执行标准的 `initialize`、`tools/list` 和 `tools/call`。MCP 路径不是普通 REST 接口，需使用支持 Streamable HTTP 的 MCP 客户端。

### 6. 启动 Go 后端

打开第二个终端：

```bash
cd backend
go mod download
go run ./cmd/server
```

默认地址：

```text
http://127.0.0.1:8080
```

Swagger：

```text
http://127.0.0.1:8080/swagger/index.html
```

如果启动时出现以下错误：

```text
AGENT_INTERNAL_TOKEN is required
```

说明 `backend/.env` 尚未配置内部密钥，或 Go 后端没有在 `backend/` 目录下启动。

### 7. 启动 React 前端

打开第三个终端：

```bash
cd frontend
npm install
npm run dev
```

默认地址：

```text
http://127.0.0.1:3000
```

前端开发服务器会把 `/api` 请求代理到 Go 后端 `127.0.0.1:8080`。

### 8. 本地调试顺序

推荐按以下顺序排查：

```text
MySQL / Redis
  -> Python Agent :8090/health
  -> Go Backend :8080
  -> React Frontend :3000
```

常用检查命令：

```bash
# Python Agent
curl http://127.0.0.1:8090/health

# Go 后端进程
curl -i http://127.0.0.1:8080/api/herbs

# 容器日志（使用 Docker 时）
docker compose logs -f mysql redis agent
```

端口被占用时：

```bash
# macOS / Linux
lsof -i :3000
lsof -i :8080
lsof -i :8090

# Linux 也可使用
ss -lntp | grep -E '3000|8080|8090'
```

停止本地 Docker 服务：

```bash
docker compose down
```

如果需要同时删除本地 Docker 数据卷：

```bash
docker compose down -v
```

> `down -v` 会删除 MySQL、Redis 和 Meilisearch 的本地数据，请谨慎执行。

### 9. 运行测试和静态检查

Python Agent（uv）：

```bash
cd agent
uv sync --dev --extra rdkit --extra embedding
uv run ruff check .
uv run mypy app tests
uv run pytest
```

如果使用 Conda：

```bash
cd agent
conda activate medical-agent
python -m pip install -e ".[rdkit]"
python -m pip install pytest ruff mypy types-openpyxl
python -m ruff check .
python -m mypy app tests
python -m pytest
```

Go 后端：

```bash
cd backend
go test ./...
go vet ./...
```

前端：

```bash
cd frontend
npm run lint
npm run build
```

---

## Windows 云服务器部署

本项目当前推荐的 Windows 单机部署方案：

```text
用户浏览器
  -> Caddy :80
       ├── 托管前端静态文件 C:\medical-agent\frontend\dist
       └── /api/* 反向代理到 Go 后端 127.0.0.1:8080
             -> MySQL84
             -> Memurai/Redis
```

实际使用组件：

| 组件 | 用途 |
|---|---|
| MySQL 8.4 / MySQL84 | 存业务数据 |
| Memurai / Redis | 缓存和限流 |
| Caddy | 托管前端、反向代理 `/api` |
| NSSM | 把 Go 后端和 Caddy 注册成 Windows 服务 |

### 1. 服务器目录

在 Windows 服务器管理员 PowerShell 中创建目录：

```powershell
New-Item -ItemType Directory -Force C:\medical-agent\backend
New-Item -ItemType Directory -Force C:\medical-agent\frontend\dist
New-Item -ItemType Directory -Force C:\medical-agent\caddy
New-Item -ItemType Directory -Force C:\medical-agent\logs
```

推荐目录结构：

```text
C:\medical-agent\
  backend\
    medicalagent-server.exe
    .env
  frontend\
    dist\
  caddy\
    Caddyfile
  logs\
  init_database_with_data_mysql_client.sql
```

### 2. 安装基础组件

安装 Chocolatey：

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

重新打开管理员 PowerShell 后验证：

```powershell
choco -v
```

安装 Memurai、Caddy、NSSM：

```powershell
choco install memurai-developer caddy nssm -y
```

如果服务器已经安装并运行 `MySQL84`，不要重复安装 Chocolatey 的 `mysql` 包。确认 MySQL 服务：

```powershell
Get-Service *mysql*
Set-Service MySQL84 -StartupType Automatic
```

启动 Memurai 并设置开机自启：

```powershell
Start-Service Memurai
Set-Service Memurai -StartupType Automatic
Test-NetConnection 127.0.0.1 -Port 6379
```

`TcpTestSucceeded : True` 表示 Redis/Memurai 可用。

验证 Caddy 和 NSSM：

```powershell
caddy version
nssm version
```

### 3. 开启 SSH 并上传文件

如需通过 `scp` 上传文件，在 Windows 服务器安装 OpenSSH Server：

```powershell
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server sshd" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
Get-Service sshd
Get-NetTCPConnection -LocalPort 22 -State Listen
```

同时需要在云厂商安全组中开放 TCP 22。建议只允许自己的公网 IP 访问。

从 macOS 本地上传 SQL：

```bash
scp /Users/bytedance/Projects/medical-agent/init_database_with_data_mysql_client.sql Administrator@39.105.221.81:/C:/medical-agent/init_database_with_data_mysql_client.sql
```

上传后端 exe：

```bash
scp /Users/bytedance/Projects/medical-agent/backend/medicalagent-server.exe Administrator@39.105.221.81:/C:/medical-agent/backend/medicalagent-server.exe
```

上传前端 dist：

```bash
scp -r /Users/bytedance/Projects/medical-agent/frontend/dist/* Administrator@39.105.221.81:/C:/medical-agent/frontend/dist/
```

### 4. 构建后端 Windows exe

在 macOS 本地交叉编译：

```bash
cd /Users/bytedance/Projects/medical-agent/backend
GOOS=windows GOARCH=amd64 /Users/bytedance/sdk/go1.26.2/bin/go build -o medicalagent-server.exe ./cmd/server
```

注意：后端入口已引入 `time/tzdata`，用于解决 Windows exe 运行时 `unknown time zone Asia/Shanghai` 问题。

### 5. 构建前端

在 macOS 本地执行：

```bash
cd /Users/bytedance/Projects/medical-agent/frontend
npm install
npm run build
```

构建产物位于：

```text
frontend/dist
```

当前前端 API 使用相对路径：

```ts
baseURL: '/api'
```

因此生产环境由 Caddy 将 `/api/*` 反向代理到后端。

### 6. 配置后端环境变量

在服务器创建：

```powershell
notepad C:\medical-agent\backend\.env
```

示例：

```env
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=ai_medical_db

REDIS_ADDR=127.0.0.1:6379
REDIS_PASSWORD=

SERVER_PORT=8080
JWT_SECRET=请换成一串足够长的随机字符串
CORS_ALLOWED_ORIGIN=http://39.105.221.81
```

生成随机 `JWT_SECRET` 的 PowerShell 命令：

```powershell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
```

### 7. 导入数据库

PowerShell 不支持直接使用 `<` 输入重定向，需要通过 `cmd /c` 执行：

```powershell
mysql -u root -p -e "DROP DATABASE IF EXISTS ai_medical_db;"
cmd /c "mysql -u root -p < C:\medical-agent\init_database_with_data_mysql_client.sql"
```

导入成功后验证：

```powershell
mysql -u root -p ai_medical_db -e "SHOW TABLES;"
mysql -u root -p ai_medical_db -e "SELECT COUNT(*) FROM herb_basic;"
mysql -u root -p ai_medical_db -e "SELECT username, role FROM users;"
```

说明：`init_database_with_data_mysql_client.sql` 是适配 Windows MySQL 客户端导入的版本，已将字符串中的 `\'` 转换为更稳妥的 `''`，避免导入时报：

```text
ERROR at line 1484: Unknown command '\''.
```

### 8. 手动测试后端

服务器 PowerShell：

```powershell
cd C:\medical-agent\backend
.\medicalagent-server.exe
```

另开 PowerShell 测试：

```powershell
curl.exe "http://127.0.0.1:8080/api/herbs?page=1&page_size=5"
curl.exe -v -X POST "http://127.0.0.1:8080/api/auth/login" -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin123\"}"
```

默认初始化账号见 SQL 文件注释，当前默认管理员为：

```text
username: admin
password: admin123
```

### 9. 配置 Caddy

服务器创建 Caddyfile：

```powershell
notepad C:\medical-agent\caddy\Caddyfile
```

使用公网 IP 访问时配置：

```caddy
:80 {
    encode gzip

    handle /api/* {
        reverse_proxy 127.0.0.1:8080
    }

    handle /swagger/* {
        reverse_proxy 127.0.0.1:8080
    }

    handle {
        root * C:\medical-agent\frontend\dist
        try_files {path} /index.html
        file_server
    }
}
```

手动测试 Caddy：

```powershell
cd C:\medical-agent\caddy
caddy run --config C:\medical-agent\caddy\Caddyfile
```

本机测试：

```powershell
curl.exe "http://127.0.0.1/api/herbs?page=1&page_size=5"
```

本地 macOS 测试公网：

```bash
curl -v "http://39.105.221.81/api/herbs?page=1&page_size=5"
```

浏览器访问：

```text
http://39.105.221.81
```

### 10. 注册 Windows 服务

不要长期在 PowerShell 前台运行后端或 Caddy。Windows 交互式终端可能阻塞 stdout/stderr，导致请求一直 pending，直到按回车或 `Ctrl+C` 才返回。应使用 NSSM 注册服务，并把日志写入文件。

注册后端服务：

```powershell
New-Item -ItemType Directory -Force C:\medical-agent\logs

nssm install MedicalAgentBackend C:\medical-agent\backend\medicalagent-server.exe
nssm set MedicalAgentBackend AppDirectory C:\medical-agent\backend
nssm set MedicalAgentBackend AppStdout C:\medical-agent\logs\backend.out.log
nssm set MedicalAgentBackend AppStderr C:\medical-agent\logs\backend.err.log
nssm set MedicalAgentBackend AppRotateFiles 1
nssm set MedicalAgentBackend AppRotateOnline 1
nssm set MedicalAgentBackend AppRotateBytes 10485760
nssm start MedicalAgentBackend
```

Chocolatey 安装的 Caddy 可能没有 `caddy service` 子命令，推荐也用 NSSM 管理：

```powershell
where.exe caddy
```

假设 Caddy 路径为 `C:\ProgramData\chocolatey\bin\caddy.exe`：

```powershell
nssm install MedicalAgentCaddy "C:\ProgramData\chocolatey\bin\caddy.exe"
nssm set MedicalAgentCaddy AppDirectory C:\medical-agent\caddy
nssm set MedicalAgentCaddy AppParameters "run --config C:\medical-agent\caddy\Caddyfile"
nssm set MedicalAgentCaddy AppStdout C:\medical-agent\logs\caddy.out.log
nssm set MedicalAgentCaddy AppStderr C:\medical-agent\logs\caddy.err.log
nssm set MedicalAgentCaddy AppRotateFiles 1
nssm set MedicalAgentCaddy AppRotateOnline 1
nssm set MedicalAgentCaddy AppRotateBytes 10485760
nssm start MedicalAgentCaddy
```

查看服务状态：

```powershell
nssm status MedicalAgentBackend
nssm status MedicalAgentCaddy
Get-NetTCPConnection -LocalPort 8080 -State Listen
Get-NetTCPConnection -LocalPort 80 -State Listen
```

查看日志：

```powershell
Get-Content C:\medical-agent\logs\backend.out.log -Tail 50
Get-Content C:\medical-agent\logs\backend.err.log -Tail 50
Get-Content C:\medical-agent\logs\caddy.out.log -Tail 50
Get-Content C:\medical-agent\logs\caddy.err.log -Tail 50
```

建议关闭 Windows 控制台 QuickEdit，避免误点窗口导致前台进程输出暂停：

```powershell
reg add HKCU\Console /v QuickEdit /t REG_DWORD /d 0 /f
```

### 11. 云服务器安全组与防火墙

阿里云安全组入方向至少开放：

```text
TCP 80   0.0.0.0/0
```

如后续使用 HTTPS，再开放：

```text
TCP 443  0.0.0.0/0
```

如需 SSH 上传文件：

```text
TCP 22   你的本地公网IP/32
```

不建议公网开放：

```text
3306 MySQL
6379 Redis
8080 Go 后端
```

Windows 防火墙开放 80：

```powershell
New-NetFirewallRule -DisplayName "Allow HTTP 80" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
```

如需 HTTPS：

```powershell
New-NetFirewallRule -DisplayName "Allow HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

### 12. 常见故障排查

按链路分段排查：

```text
浏览器 -> Caddy :80 -> Go 后端 :8080 -> MySQL/Redis
```

后端本机直连：

```powershell
curl.exe "http://127.0.0.1:8080/api/herbs?page=1&page_size=5"
```

Caddy 本机反代：

```powershell
curl.exe "http://127.0.0.1/api/herbs?page=1&page_size=5"
```

公网访问：

```bash
curl -v "http://39.105.221.81/api/herbs?page=1&page_size=5"
```

判断规则：

```text
第一条失败：后端未运行、端口不对、数据库连接失败或后端内部错误
第一条成功，第二条失败：Caddyfile 或 Caddy 服务问题
前两条成功，第三条失败：阿里云安全组或 Windows 防火墙问题
三条都成功，浏览器失败：前端缓存、前端 dist 版本或浏览器请求问题
```

查看浏览器实际请求地址：

```text
F12 -> Network -> Request URL
```

正确地址应为：

```text
http://39.105.221.81/api/...
```

如果看到：

```text
http://localhost:8080/api/...
```

说明前端构建产物不是最新版本，需要重新 `npm run build` 并上传 `dist`。

如果登录请求长时间 pending，但后端日志只有按回车或 `Ctrl+C` 后才刷新，多半是前台 PowerShell 控制台阻塞输出。应停止前台运行，改用 NSSM 服务运行并写文件日志。

## 中间件使用情况

当前项目处于 Phase 1（CRUD Web 应用），已使用 **MySQL** 作为主数据库，并使用 **Redis/Memurai** 做公共资源缓存和 IP 限流。

| 组件 | 状态 | 说明 |
|---|---|---|
| MySQL | 已使用 | GORM 驱动，config.go 中 DSN 连接 |
| Redis | 已使用 | 缓存 herbs、decoctions、couplets、compounds、expertises、papers 的列表/详情，并用于 IP 限流 |
| RocketMQ | 规划接入 | 配置与容器编排已就绪；MVP 暂保留 HTTP 调度，后续用于异步任务与事件流 |
| Meilisearch | 未使用 | 未接入，中文全文检索待 Phase 2 |
| Caddy | 生产部署使用 | Windows 云服务器中托管前端静态文件，并反向代理 `/api/*` 到 Go 后端 |
| Nginx | 未使用 | 可作为 Caddy 替代方案，当前部署未采用 |

Redis 可自动降级：未配置或连接失败时，不影响 MySQL 主查询流程，只是缓存和 Redis 限流不可用。

## Agent MVP 与管理员 LLM 配置

1. 在 Go 后端运行环境设置 `LLM_ENCRYPTION_KEY`。该值必须是 32 字节原文或 Base64 编码的 32 字节随机值，可使用 `openssl rand -base64 32` 生成；不要提交到 Git。
2. 确保 Go 后端与 Python Agent 使用相同的 `AGENT_INTERNAL_TOKEN`。
3. 设置 `AGENT_LLM_MODE=optional`，LLM 不可用时仍返回确定性分析结果；生产强校验可改为 `required`。
4. 管理员登录后进入“LLM 配置”，填写 OpenAI 兼容 API 的 Base URL（通常包含 `/v1`）、API Key 和模型名。
5. 普通登录用户进入“智能分析”创建任务并查看工作流、结构化证据与 LLM 中文摘要。

API Key 仅由 Go 服务使用 `AES-256-GCM` 加密后存入数据库。前端、Python Agent、任务 Payload 和查询接口均不会获得或回显明文密钥。

消息队列已统一为 RocketMQ。当前 MVP 为保证演示稳定，Agent Run 继续使用同步 HTTP 调度；可通过 `docker compose --profile mq up -d rocketmq-namesrv rocketmq-broker` 启动预留的 RocketMQ 5 基础设施，后续再迁移为生产者/消费者链路。

### 对话式 ReAct Agent

`/agent` 已升级为多轮聊天工作台。新链路不再执行固定七节点流程，而是使用 LangGraph 的 `agent → tools → agent` 条件循环：LLM 根据用户问题自主决定直接回答或调用只读/计算工具；工具结果会回传给 LLM 继续判断，直到形成最终回答。旧 `/api/agent/runs` 和固定科研工作流继续保留用于兼容。

当前聊天工具白名单包括药名标准化、业务数据库知识检索和基于毒理索引的向量检索。每个 Turn 最多 8 轮 LLM 推理、12 次工具调用；节点开始/结束、LLM 请求和工具调用结果以事件形式持久化并在前端动态展示。

LLM 回答通过 `LLM API → Go 安全代理 → Python Agent → Go Turn SSE → React` 全链路流式输出。前端使用 `react-markdown + remark-gfm` 安全渲染 Markdown/GFM，支持标题、列表、表格、引用、代码块与链接，不启用原始 HTML。SSE 断线时自动回退到 Turn 轮询，并避免重复 token 或重复消息。
