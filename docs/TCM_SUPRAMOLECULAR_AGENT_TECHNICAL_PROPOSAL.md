# 中药超分子实验智能体平台技术方案

> 项目：`medical-agent` 2.0 / TCM Supramolecular Research Agent  
> 作者：杨知愚  
> 状态：架构与技术选型已确认  
> 定位：60% Agent 系统工程 + 40% 科研智能推理  
> 文档版本：v1.0  
> 日期：2026-08-08

## 1. 方案摘要

本项目将在现有 `medical-agent` 中医药知识平台基础上，新增一个独立的 Python Agent 服务，把现有的知识库 CRUD 平台升级为“面向中药超分子实验设计的可验证、多智能体科研平台”。

平台保留已有的 React、Go、MySQL 主架构。Go 服务继续负责用户、权限、业务数据、任务记录和统一 API；Python 服务负责 Agent 编排、文献检索、分子计算、证据校验和实验建议生成。前端不直接访问 Python 服务，所有用户请求均通过 Go API 进入，以保持统一鉴权、审计和接口边界。

项目不以“调用大模型生成一段建议”为目标，而是重点实现以下能力：

- 基于 LangGraph 的有状态、可暂停、可恢复、可回放科研工作流；
- 基于 MCP 的标准化科学工具平台；
- 基于五层记忆、Context Manager 与 Skill Runtime 的可扩展 Agent 能力体系；
- 基于 RDKit、混合检索和 GraphRAG 的科研推理链路；
- 基于 Chain-of-Evidence 的结论—证据可追溯机制；
- 基于 OpenTelemetry、Langfuse 的跨 Go/Python 全链路观测；
- 基于 DeepEval、Ragas 和人工金标集的 Agent 评测体系；
- 基于 Human-in-the-loop 的候选成分确认与实验方案审核；
- 可量化、可演示、可在面试中深入解释的 Agent 工程实践。

核心编排只采用 LangGraph。CrewAI、AutoGen 等框架不进入主链路，只用于后续框架对比实验，避免技术堆砌。

## 2. 项目背景与现状

### 2.1 现有平台能力

当前 `medical-agent` 已具备较完整的中医药知识平台基础：

- React 18、TypeScript、Vite、Ant Design 前端；
- Go、Gin、GORM 后端；
- MySQL 业务数据库；
- Redis 缓存和限流；
- JWT 登录与权限控制；
- Swagger API 文档和 Zap 日志；
- 中药、方剂、药对、化合物、文献和专家经验等业务模块；
- `molecular_info` 中已有 SMILES、InChI 等化学结构字段；
- Docker Compose 本地基础设施；
- 前端列表、详情、搜索、分页和 CRUD 交互。

现有平台适合作为用户、数据和业务管理底座，不需要推翻重建。

### 2.2 当前缺口

当前系统的主要问题不是业务页面不足，而是缺少完整的 Agent 工程能力：

- 没有持久化的 Agent 运行状态；
- 没有失败恢复、断点续跑和人工审批；
- 没有标准化工具协议；
- 没有科研级混合检索和分子相似检索；
- 没有结论到原始证据的强关联；
- 没有跨 React、Go、Python、LLM 和工具的全链路追踪；
- 没有可重复运行的 Agent Benchmark；
- 没有结构化保存中间结果和实验方案版本；
- 尚未把现有中药、化合物和文献数据转化为智能推理能力。

## 3. 建设目标与边界

### 3.1 建设目标

平台需要完成以下业务闭环：

1. 用户输入一味或多味中药，也可从现有知识库选择；
2. 系统完成中英文名称、别名和实体标准化；
3. 从本地数据库以及 HERB、TCMSP、PubChem 等数据源获取候选成分；
4. 用户确认本次参与分析的候选成分；
5. 系统校验 SMILES，计算分子描述符和分子指纹；
6. 从本地 Excel、已有文献库及后续 PDF 知识库检索相似案例；
7. 综合语义相似度、关键词匹配、实体匹配和分子相似度重排；
8. 根据文献证据和可解释规则生成候选实验条件；
9. 证据校验节点检查每项结论是否有可靠依据；
10. 研究人员审核、修改或退回方案；
11. 平台保存实验方案、证据链、模型版本、工具输出和运行轨迹。

### 3.2 技术目标

- Agent 任务支持暂停、恢复、重试和节点级回放；
- 所有 LLM 节点输出均通过 Pydantic Schema 校验；
- 科学计算由 RDKit 等确定性工具完成，LLM 不替代科学计算；
- 每条实验建议至少关联一项文献、分子计算或规则证据；
- Go 和 Python 之间透传统一 `trace_id`、`run_id` 和用户上下文；
- 评测结果可用于 PR 回归和不同策略的横向对比；
- 模型、Embedding、Reranker 和工具均可替换，不绑定单一厂商。

### 3.3 非目标

第一阶段明确不做以下事项：

- 不同时使用 LangGraph、CrewAI 和 AutoGen 编排主流程；
- 不在第一版引入 Kubernetes；
- 不为了展示技术而强行引入 RocketMQ；
- 不建设无人监督、长期自主运行的开放式 Agent；
- 不让 LLM 代替 RDKit、规则引擎和数据库事实；
- 不把所有工作流节点都设计成 LLM Agent；
- 不在混合检索完成前优先建设复杂 GraphRAG；
- 不使用同一个 Agent 实例完成生成和质量评审；
- 不在没有真实评测数据时编造性能或准确率指标。

## 4. 设计原则

### 4.1 一个核心编排框架

LangGraph 是唯一主编排框架，负责状态、节点、分支、Checkpoint、人工中断和恢复。PydanticAI 或普通 Pydantic 用于节点内部的强类型输入输出，不承担全局编排。

### 4.2 确定性工具优先

可通过数据库、API、规则或科学计算得到的结果，不交给 LLM 猜测。例如分子量、LogP、TPSA、分子指纹、Tanimoto 相似度和规则评分必须由确定性工具产生。

### 4.3 生成与验证分离

实验方案生成节点和证据验证节点采用不同 Prompt、不同 Agent 实例，条件允许时使用不同模型，减少“自己证明自己”的反馈污染。

### 4.4 证据优先于答案

平台交付的核心不是一段自然语言，而是结构化实验方案及其证据关系。无法找到证据时，系统必须显式标记为假设或不确定性。

### 4.5 协议与实现解耦

科研工具通过 MCP 暴露，工作流不直接依赖工具内部实现。模型通过统一 Provider Adapter 或 LiteLLM 接入，避免绑定模型厂商。

### 4.6 可观测性和评测从第一天开始

Agent Trace、工具调用、Token、成本、延迟和质量评分不是上线后的补充功能，而是第一阶段必须具备的基础能力。

## 5. 总体架构

```text
用户浏览器
   |
   v
React + TypeScript 前端
   |
   | REST / Task Polling / SSE（后续）
   v
Go API Gateway（Gin）
   |-- JWT / RBAC / 审计
   |-- 知识库 CRUD
   |-- 实验项目与任务管理
   |-- Agent Run 管理
   |-- MySQL / Redis
   |
   | 内部 HTTP 或 gRPC
   v
Python Agent Service（FastAPI）
   |-- LangGraph 工作流
   |-- Pydantic 结构化输出
   |-- LiteLLM 模型适配
   |-- Celery Worker（中长任务）
   |
   +--> MCP Tool Servers
   |      |-- TCM Database MCP
   |      |-- Chemistry MCP / RDKit
   |      |-- Literature MCP
   |      |-- Experiment Scoring MCP
   |
   +--> Retrieval
   |      |-- Qdrant Dense/Sparse
   |      |-- BGE-M3 Embedding
   |      |-- BGE Reranker
   |      |-- Neo4j GraphRAG（第二阶段）
   |
   +--> Knowledge Ingestion
   |      |-- Excel Loader
   |      |-- Docling PDF Parser（第二阶段）
   |
   +--> AgentOps
          |-- OpenTelemetry Collector
          |-- Langfuse
          |-- Prometheus / Grafana（增强）
          |-- DeepEval / Ragas
```

### 5.1 服务职责

| 服务 | 主要职责 | 不负责的事项 |
|---|---|---|
| React 前端 | 用户操作、任务进度、候选成分确认、证据展示、实验方案审核 | 不直接调用 Python Agent 或外部模型 |
| Go API | 鉴权、权限、业务数据、任务生命周期、审计、统一对外 API | 不执行 RDKit 和复杂 Agent 推理 |
| Python Agent | 工作流编排、RAG、分子计算调度、规则评分、LLM 推理、证据校验 | 不重复实现用户、权限和业务 CRUD |
| MCP Servers | 以标准协议提供科研工具 | 不负责全局工作流状态 |
| MySQL | 业务数据和 Agent 最终状态的单一事实来源 | 不承担向量相似搜索 |
| Qdrant | Dense/Sparse 向量检索 | 不作为业务主数据库 |
| Neo4j | 关系推理和 GraphRAG | 第一阶段不承担核心检索 |
| Redis | 缓存、限流、任务队列和短期状态 | 不保存最终业务结果 |
| Langfuse | LLM/Agent Trace、成本、Prompt 版本和质量分数 | 不作为业务数据库 |

## 6. Agent 工作流

### 6.1 LangGraph 状态节点

主工作流建议拆为以下节点：

1. `InputNormalizer`：解析草药、药对、方剂和研究目标；
2. `EntityResolver`：匹配本地实体、别名和标准名；
3. `CompoundDiscovery`：查询本地库和外部数据源；
4. `CompoundConfirmation`：通过 `interrupt()` 暂停，等待用户确认；
5. `ChemistryAnalysis`：调用 RDKit 校验结构并计算特征；
6. `ResearchPlanner`：将研究问题拆解为检索子问题；
7. `LiteratureRetriever`：执行结构化、语义和关键词检索；
8. `MolecularReranker`：融合分子结构相似度；
9. `RuleScorer`：执行可解释规则评分；
10. `ExperimentDesigner`：生成候选形貌、条件和操作步骤；
11. `EvidenceVerifier`：核查每条结论和引用；
12. `HumanReview`：研究人员审核、修改或退回；
13. `ReportAssembler`：形成最终结构化实验方案；
14. `PersistenceNode`：保存结果、证据和运行摘要。

### 6.2 工作流状态

建议定义统一状态模型：

```python
class AgentState(TypedDict):
    run_id: str
    user_id: int
    research_goal: str
    herbs: list[HerbRef]
    candidate_compounds: list[CompoundCandidate]
    confirmed_compound_ids: list[str]
    molecule_features: list[MoleculeFeature]
    retrieval_queries: list[str]
    retrieved_evidence: list[EvidenceItem]
    rule_scores: list[RuleScore]
    proposal: ExperimentProposal | None
    verification: VerificationResult | None
    human_decision: HumanDecision | None
    errors: list[StepError]
    trace_id: str
```

状态中只保存可序列化对象。大文件、图片和长文档保存到文件存储，通过 ID 引用，避免 Checkpoint 过大。

### 6.3 Agent 与工具的边界

- Planner、Experiment Designer 和 Evidence Verifier 可以调用 LLM；
- 输入标准化可先使用规则和数据库，必要时调用小模型；
- RDKit、数据库、向量搜索、规则评分都是工具节点；
- Reporter 只负责表达和组装，不新增未经验证的事实；
- Human Review 是正式状态节点，不是前端临时弹窗。

## 7. MCP 工具平台

### 7.1 MCP Server 划分

#### TCM Database MCP

- `search_herbs`
- `get_herb`
- `search_formulas`
- `search_compounds`
- `get_herb_compound_relations`
- `get_compound_evidence`

#### Chemistry MCP

- `normalize_smiles`
- `validate_smiles`
- `calculate_descriptors`
- `calculate_morgan_fingerprint`
- `calculate_tanimoto_similarity`
- `render_2d_structure`
- `batch_compare_molecules`

#### Literature MCP

- `search_literature`
- `hybrid_retrieve`
- `get_document_chunk`
- `get_document_metadata`
- `verify_citation`
- `retrieve_similar_experiments`

#### Experiment MCP

- `apply_assembly_rules`
- `score_candidate`
- `propose_condition_grid`
- `validate_condition_range`
- `compare_experiment_proposals`

### 7.2 MCP 接口要求

每个工具必须定义：

- 明确的 Pydantic 输入和输出 Schema；
- 超时、重试和幂等策略；
- 工具版本；
- 数据来源和更新时间；
- 错误码而不是模糊自然语言错误；
- OpenTelemetry Span；
- 可脱离 LLM 运行的单元测试；
- 对高风险操作的权限检查。

### 7.3 MCP 与 A2A 的边界

MCP 用于 Agent 调用工具和数据源，是核心必选协议。A2A 用于两个独立部署、独立拥有状态和权限边界的 Agent 系统之间进行任务委派。

第二阶段可将“深度文献研究 Agent”独立部署为 A2A Peer。主工作流内部节点不使用 A2A，避免把本地函数调用过度服务化。

## 8. 分子计算与规则评分

### 8.1 RDKit 能力

RDKit 负责：

- SMILES 解析和标准化；
- InChIKey 生成；
- 分子量、LogP、TPSA；
- 氢键供体和受体；
- 可旋转键、芳香环、电荷；
- Morgan Fingerprint；
- Tanimoto Similarity；
- 二维结构图生成；
- 重复结构识别和盐形式处理。

计算结果应保存 RDKit 版本、参数版本和计算时间，确保结果可复现。

### 8.2 规则引擎

规则引擎使用可配置 YAML 或数据库配置，不把权重硬编码在 Prompt 中。初步评分维度包括：

- 氢键网络形成潜力；
- 芳香结构与 π-π 堆积潜力；
- 疏水作用；
- 离子配对和电荷互补；
- 金属配位位点；
- 分子柔性和构象稳定性；
- 与文献案例的分子相似度；
- 已知形貌和实验条件匹配度。

规则输出必须包含分数、命中规则、正负影响和适用范围。规则评分是建议依据之一，不作为真实实验结论。

## 9. 科研级 RAG 设计

### 9.1 知识来源

第一阶段：

- 现有 131 条 Excel 文献数据；
- MySQL 中已有中药、化合物和文献数据；
- PubChem 等外部结构化数据。

第二阶段：

- 用户上传 PDF；
- PubMed/arXiv 等公开论文元数据；
- 补充实验记录和人工反馈；
- Neo4j 中药—成分—组装—证据关系图。

### 9.2 文档摄取

Excel 导入流程：

1. 字段映射和清洗；
2. 文献 ID、DOI 和标题去重；
3. 中药、成分、形貌、相互作用和条件实体提取；
4. 生成适合检索的文档文本；
5. 生成 Dense 和 Sparse 向量；
6. 写入 Qdrant；
7. 保存 `doc_id`、`content_hash`、`version_id` 和索引状态。

PDF 导入流程在第二阶段使用 Docling，保留页码、章节、表格位置和原始文件坐标，以便引用回溯。

### 9.3 混合检索链路

```text
研究问题
  -> 中药/成分实体识别
  -> MySQL 条件过滤
  -> Dense Retrieval（BGE-M3）
  -> Sparse Retrieval（BM25/SPLADE）
  -> RRF 融合
  -> BGE Reranker
  -> RDKit 分子相似度重排
  -> Neo4j 关系扩展（第二阶段）
  -> Evidence Items
```

建议的初始融合权重为：

```text
语义相似度       35%
关键词匹配       20%
中药/成分匹配    20%
分子结构相似度   20%
年份与完整度      5%
```

权重只是初始配置，最终必须由人工金标集和离线评测确定。

### 9.4 Qdrant 与 Neo4j 的边界

- Qdrant 保存向量和检索元数据；
- Neo4j 保存实体和关系；
- MySQL 保存业务实体与事务数据；
- 同一份向量不同时写入 Neo4j 和 Qdrant承担相同检索职责；
- LlamaIndex 只作为摄取、索引和 Property Graph 适配层，不与 LangChain 重复封装同一检索器。

## 10. Chain-of-Evidence 证据链

### 10.1 目标

每个实验建议都能回答：

- 这条结论由谁生成？
- 使用了哪个模型和 Prompt 版本？
- 调用了哪些工具？
- 使用了哪些文献片段？
- 命中了哪些分子特征和规则？
- 是否经过人工审核？
- 还有哪些不确定性？

### 10.2 证据对象

```python
class EvidenceItem(BaseModel):
    evidence_id: str
    evidence_type: Literal[
        "literature", "molecular_calculation", "rule", "database", "human"
    ]
    source_id: str
    source_title: str | None
    quote: str | None
    page: int | None
    tool_name: str | None
    tool_version: str | None
    trace_span_id: str
    confidence: float
```

### 10.3 结论对象

```python
class SupportedClaim(BaseModel):
    claim_id: str
    claim: str
    claim_type: Literal[
        "morphology", "condition", "interaction", "procedure", "risk"
    ]
    evidence_ids: list[str]
    confidence: float
    uncertainty: str | None
    verification_status: Literal[
        "supported", "partially_supported", "hypothesis", "rejected"
    ]
```

### 10.4 校验规则

- 无 `evidence_ids` 的事实型结论不能进入最终方案；
- 推测允许保留，但必须标记为 `hypothesis`；
- DOI、标题、页码和引文需与原始文档校验；
- Evidence Verifier 不允许新增事实；
- 人工修改必须保留修改前后版本；
- 最终页面支持从结论跳转到证据和 Langfuse Span。

## 11. 模型与 Prompt 管理

### 11.1 LiteLLM 模型网关

LiteLLM 或自定义 Provider Adapter 负责：

- 接入 OpenAI、Claude、豆包和本地模型；
- 统一模型参数和错误格式；
- 根据节点选择模型；
- Fallback 和重试；
- Token 与成本预算；
- 模型调用日志；
- 测试环境使用 Mock Provider。

### 11.2 节点模型路由

| 节点 | 推荐模型类型 | 原因 |
|---|---|---|
| 输入标准化 | 小模型或规则 | 成本低、任务简单 |
| Research Planner | 中等推理模型 | 需要任务分解能力 |
| 文献摘要 | 长上下文模型 | 需要处理证据片段 |
| Experiment Designer | 强推理模型 | 核心科研推理节点 |
| Evidence Verifier | 与生成节点不同的模型 | 降低自评偏差 |
| Reporter | 中等模型 | 只做结构化表达 |

### 11.3 Prompt 版本化

每个 Prompt 需要保存：

- `prompt_name`；
- `prompt_version`；
- 输入和输出 Schema；
- 适用模型；
- 关联评测集；
- 发布状态；
- 变更说明。

Prompt 变更必须运行离线回归，不允许直接覆盖生产版本。

## 12. 数据模型

### 12.1 Agent 任务

建议新增：

- `agent_runs`：一次完整运行；
- `agent_run_steps`：节点级状态、输入、输出、耗时和错误；
- `agent_checkpoints`：可恢复状态引用；
- `agent_artifacts`：结构图、报告和中间文件；
- `human_reviews`：人工确认和审核记录。

### 12.2 中药与成分关系

增加通用关联，不局限于毒性成分：

- `herb_compound_relations`；
- 来源数据库和外部 ID；
- 关系证据；
- 可信度；
- 是否人工确认；
- 数据版本和更新时间。

### 12.3 分子计算

新增：

- `molecule_descriptors`；
- 标准化 SMILES 和 InChIKey；
- 描述符 JSON；
- Fingerprint 存储引用；
- RDKit 版本；
- 参数版本；
- 计算时间。

### 12.4 实验方案

新增：

- `experiment_proposals`；
- `experiment_conditions`；
- `proposal_claims`；
- `proposal_evidence`；
- `proposal_versions`；
- `experiment_feedback`。

### 12.5 知识库

新增：

- `knowledge_documents`；
- `knowledge_chunks`；
- `document_versions`；
- `index_jobs`；
- `index_failures`。

Qdrant 保存向量，MySQL 保存文档和 Chunk 的业务元数据以及索引状态。

## 13. API 设计

### 13.1 面向前端的 Go API

```text
POST   /api/agent/runs
GET    /api/agent/runs
GET    /api/agent/runs/:id
GET    /api/agent/runs/:id/steps
POST   /api/agent/runs/:id/cancel
POST   /api/agent/runs/:id/retry
POST   /api/agent/runs/:id/confirm-compounds
POST   /api/agent/runs/:id/review
GET    /api/agent/runs/:id/evidence
GET    /api/experiment-proposals/:id
GET    /api/experiment-proposals/:id/versions
POST   /api/knowledge/documents
GET    /api/knowledge/index-jobs/:id
```

### 13.2 Go 到 Python 的内部 API

```text
POST   /internal/v1/runs
GET    /internal/v1/runs/:id
POST   /internal/v1/runs/:id/resume
POST   /internal/v1/runs/:id/cancel
POST   /internal/v1/runs/:id/retry-step
GET    /internal/v1/runs/:id/artifacts
GET    /internal/v1/health
```

请求必须携带：

- `run_id`；
- `traceparent`；
- `user_id`；
- `tenant_id`（为未来多租户预留）；
- `request_id`；
- 内部服务签名或 Token。

第一阶段使用内部 HTTP，降低开发和调试成本；确认性能或流式要求后，再评估 gRPC。Agent 长任务不保持同步 HTTP 连接，由 Go 创建任务后轮询或订阅状态。

## 14. 前端产品设计

### 14.1 复用现有能力

复用现有：

- 登录、注册和权限路由；
- `Layout.tsx`；
- Axios API 封装；
- 列表和详情页面模式；
- `Section.tsx` 信息区块；
- Ant Design 组件和全局样式。

### 14.2 新增页面

#### Agent 工作台

- 选择中药、药对或方剂；
- 输入研究目标；
- 选择快速分析或深度研究；
- 设置可选限制条件；
- 发起 Agent 任务。

#### 候选成分确认页

- 成分名称和来源；
- SMILES、分子式、分子量；
- 二维结构图；
- 中药关联证据；
- 用户勾选、排除或补充成分。

#### Agent 运行详情页

- LangGraph 节点进度；
- 每个节点的状态、耗时和重试次数；
- 工具调用摘要；
- 错误和恢复记录；
- Langfuse Trace 跳转。

#### 实验方案详情页

- 研究对象；
- 候选形貌；
- 浓度、比例、溶剂、pH 和温度；
- 操作步骤；
- 表征方法；
- 风险与不确定性；
- 结论—证据关联；
- 人工审核和版本记录。

#### 知识库管理页

- Excel/PDF 上传；
- 文档解析和索引进度；
- 数据版本；
- 失败记录；
- 重建索引。

#### 评测与对比页

- Baseline 与各版本指标；
- 检索 Recall@K、MRR、NDCG；
- Tool Call Accuracy；
- 引用正确率和完整率；
- 延迟、成本和错误恢复率；
- 不同模型和 Prompt 的对比。

## 15. 异步任务与状态一致性

### 15.1 任务方案

第一阶段采用 Redis + Celery：

- Go 创建 `agent_run`；
- Go 调用 Python 创建工作流；
- Python 投递 Celery 任务；
- LangGraph Checkpointer 保存节点状态；
- MySQL 保存最终业务状态；
- Redis 保存队列和短期进度；
- 前端轮询 Go API；
- 后续增加 SSE 推送。

现有架构已确定后续使用 RocketMQ，但当前规模没有必要立即引入完整消息链路。RocketMQ 在后续出现高吞吐事件流、多个异构消费者和严格事件回放需求时接入；MVP 继续使用 HTTP 调度。

### 15.2 一致性原则

- MySQL 中的 `agent_runs.status` 是对用户可见的最终状态；
- LangGraph Checkpoint 是工作流恢复状态；
- Redis 状态可丢失，不作为最终事实；
- Python 节点必须幂等；
- 外部 API 响应保留内容哈希和缓存时间；
- 向量索引采用版本号和软删除；
- Go 调用 Python 使用幂等键，避免重复创建任务。

## 16. 可观测性与 AgentOps

### 16.1 OpenTelemetry 链路

统一 Trace 路径：

```text
React Request
  -> Go Handler
  -> Go Agent Client
  -> Python FastAPI
  -> Celery Task
  -> LangGraph Node
  -> LLM / MCP Tool / Qdrant / RDKit
```

所有服务透传 W3C Trace Context。OpenTelemetry Collector 统一接收 Go 和 Python Span，再转发到 Langfuse、Prometheus 或其他后端。

### 16.2 Langfuse 记录内容

- Agent Run 和节点 Span；
- 模型、Prompt 版本和参数；
- Token 用量和成本；
- 工具名称、参数摘要和错误；
- 检索结果和评分；
- 输出 Schema 校验结果；
- 人工审核结果；
- 离线评测分数。

敏感数据在进入 Langfuse 前脱敏，禁止记录密码、Token 和完整隐私字段。

### 16.3 关键指标

- Agent 任务成功率；
- 节点失败率；
- 错误恢复率；
- 平均重试次数；
- P50/P95 端到端延迟；
- 每次任务 Token 和费用；
- Schema 通过率；
- Tool Call Accuracy；
- 引用正确率和完整率；
- 人工修改率；
- 平均 Agent 迭代次数。

指标目标必须先测量 Baseline，再根据实际结果设定，不能直接把行业示例数字写成项目成绩。

## 17. 评测体系

### 17.1 金标数据集

从 131 篇现有文献中构建 30～50 个第一版样本，每个样本包含：

- 输入中药或组合；
- 正确或可接受的关键成分；
- 应召回文献；
- 已知组装形貌；
- 已知溶剂、pH、温度和浓度；
- 已知相互作用；
- 可接受的实验建议范围；
- 明确禁止的无依据结论；
- 专家评分或人工审阅意见。

### 17.2 评测维度

#### 检索评测

- Recall@K；
- Precision@K；
- MRR；
- NDCG；
- 分子相似案例命中率。

#### Agent 评测

- Agent Goal Accuracy；
- Tool Call Accuracy；
- Tool 参数正确率；
- 节点完成率；
- 错误恢复率；
- 平均迭代次数。

#### 证据评测

- 引用存在率；
- 引用正确率；
- 引用完整率；
- Claim—Evidence 一致性；
- 无证据事实比例。

#### 实验方案评测

- 条件合法性；
- 条件范围合理性；
- 形貌假设与证据一致性；
- 不确定性披露完整度；
- 专家修改率；
- 专家综合评分。

### 17.3 对照实验

```text
Baseline：单 Agent + Dense 向量检索
V1：LangGraph + Dense/Sparse 混合检索
V2：V1 + Cross-Encoder Reranker
V3：V2 + RDKit 分子相似度重排
V4：V3 + Chain-of-Evidence + Evidence Verifier
V5：V4 + Neo4j GraphRAG
```

使用同一测试集和固定模型参数对比，记录质量、延迟和成本。框架对比实验可使用同一子任务分别运行 LangGraph、CrewAI 和 AutoGen，但不改变生产主链路。

## 18. 安全、权限与科研风险

- 外部 API Key 仅通过环境变量或 Secret 管理；
- MCP 工具按角色授权；
- 高成本和高风险工具需要预算和人工确认；
- 上传文件需要类型、大小和恶意内容检查；
- 模型输出经过 Schema、语义和业务规则三层校验；
- 最终页面明确提示“建议不替代真实实验”；
- 文献引用必须可验证；
- Prompt Injection 文本不得直接改变系统策略；
- 研究员人工审核是正式发布实验方案的必经门；
- 所有人工修改和模型输出保留版本与审计记录。

## 19. 代码目录规划

```text
medical-agent/
├── frontend/                       # 现有 React 前端
│   └── src/
│       ├── pages/
│       │   ├── AgentWorkspace/
│       │   ├── AgentRunDetail/
│       │   ├── CompoundConfirmation/
│       │   ├── ExperimentProposal/
│       │   ├── KnowledgeManagement/
│       │   └── EvaluationDashboard/
│       ├── components/
│       ├── services/
│       └── types/
├── backend/                        # 现有 Go 主后端
│   ├── cmd/server/
│   └── internal/
│       ├── handler/
│       ├── service/
│       ├── repository/
│       ├── model/
│       ├── client/agent/           # Python Agent Client
│       └── telemetry/
├── agent/                          # 新增 Python Agent 服务
│   ├── app/
│   │   ├── api/
│   │   ├── workflows/
│   │   │   ├── state.py
│   │   │   ├── graph.py
│   │   │   └── nodes/
│   │   ├── agents/
│   │   ├── memory/              # 五层记忆、作用域与召回
│   │   ├── context/             # Context Manager 与 Token Budget
│   │   ├── skills/              # Skill Registry、Router、Runtime
│   │   ├── mcp_servers/
│   │   │   ├── tcm_database/
│   │   │   ├── chemistry/
│   │   │   ├── literature/
│   │   │   └── experiment/
│   │   ├── retrieval/
│   │   ├── evidence/
│   │   ├── rules/
│   │   ├── providers/
│   │   ├── schemas/
│   │   ├── workers/
│   │   ├── telemetry/
│   │   └── main.py
│   ├── skills/                   # 版本化 Skill 能力包
│   │   ├── compound-discovery/
│   │   ├── molecular-analysis/
│   │   ├── literature-research/
│   │   ├── experiment-design/
│   │   └── evidence-verification/
│   ├── evals/
│   │   ├── datasets/
│   │   ├── metrics/
│   │   └── experiments/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── data/
│   ├── seed/
│   ├── uploads/
│   └── eval/
├── scripts/
│   ├── import_literature.py
│   ├── rebuild_index.py
│   └── run_evaluation.py
├── docs/
│   └── TCM_SUPRAMOLECULAR_AGENT_TECHNICAL_PROPOSAL.md
├── docker-compose.yml
└── README.md
```

现有 `tcm-supramolecular-agent` 原型代码按以下方式迁移：

- `herb_lookup.py` → `agent/app/mcp_servers/tcm_database/`；
- `mol_features.py` → `agent/app/mcp_servers/chemistry/`；
- `rag_engine.py` → `agent/app/retrieval/`；
- `rule_scorer.py` → `agent/app/rules/`；
- `llm_advisor.py` → 拆分到 `providers/` 和工作流节点；
- `pipeline.py` → 重构为 LangGraph `graph.py` 和节点模块。

## 20. 部署方案

### 20.1 本地开发

Docker Compose 管理：

- MySQL；
- Redis；
- Qdrant；
- Neo4j（第二阶段 Profile）；
- Langfuse；
- OpenTelemetry Collector；
- Go API；
- Python Agent；
- Celery Worker；
- React 前端。

基础模式只启动 MySQL、Redis、Qdrant、Go 和 Python。Neo4j、Langfuse、Grafana 等通过 Compose Profile 可选启动，降低本地资源压力。

### 20.2 生产部署

第一版继续支持现有单机部署思路：

- Caddy/Nginx 统一入口；
- React 静态文件；
- Go API 服务；
- Python Agent 服务；
- Celery Worker；
- MySQL、Redis、Qdrant；
- 独立数据卷和日志目录。

当并发、团队规模和运行任务数量达到瓶颈后再评估 Kubernetes，不把容器编排作为第一版目标。

## 21. 分阶段实施计划

### P0：Agent 工程骨架

目标：让一条最小科研工作流可运行、可观察、可恢复。

交付内容：

- 新增 Python FastAPI 服务；
- Go Agent Client；
- LangGraph 状态、Checkpoint 和基础节点；
- 工作记忆接口与 Run/Project/User 作用域定义；
- Context Manager 基础版与节点级 Token Budget；
- Skill Manifest、Registry 和一个最小内置 Skill；
- Pydantic 输入输出；
- PubChem 和 RDKit 工具；
- Qdrant 基础检索；
- OpenTelemetry + Langfuse；
- Agent Run 页面；
- 基础单元测试和端到端测试。

完成标准：

- 可输入一味中药并产生结构化建议；
- 可查看节点进度和 Trace；
- 任务失败后可重试；
- 所有节点输出通过 Schema 校验；
- 最终结果保存到 MySQL。

### P1：可信科研闭环

目标：完成真正可演示的中药超分子实验设计流程。

交付内容：

- 131 条 Excel 文献导入；
- Dense/Sparse/RRF/Reranker 混合检索；
- RDKit 分子相似度重排；
- MCP 工具服务；
- 五层记忆的写入、召回、失效和权限控制；
- Context 压缩、证据保留与上下文评测；
- 首批六个内置 Skill 及发布评测流程；
- Chain-of-Evidence；
- Evidence Verifier；
- 候选成分确认；
- Human-in-the-loop 审核；
- Ragas/DeepEval 评测；
- 30～50 条金标测试集。

完成标准：

- 每条事实型建议均有关联证据；
- 可从结论跳转到文献片段或计算结果；
- 完成 Baseline、V1～V4 对照实验；
- README 展示真实指标、架构和演示流程；
- 支持完整 Demo 录屏。

### P2：前沿能力增强

目标：增加知识推理深度和生态互操作能力。

交付内容：

- Docling PDF 文献摄取；
- Neo4j 中药超分子知识图谱；
- LlamaIndex PropertyGraphIndex；
- GraphRAG；
- A2A 文献研究 Agent；
- 多模型路由和成本预算；
- CrewAI/AutoGen 离线框架对比；
- 实验反馈闭环；
- SSE 实时进度；
- Prometheus/Grafana 运行大盘。

完成标准：

- GraphRAG 相对 V4 有可量化增益；
- A2A 仅用于独立 Agent 委派；
- PDF 引文可定位到页码；
- 可演示模型、检索和 Prompt A/B 测试。

## 22. 测试策略

### 22.1 Python

- `pytest` 单元测试；
- MCP 工具契约测试；
- LangGraph 节点和状态迁移测试；
- 外部 API 使用 Mock 或录制响应；
- RDKit Golden Test；
- 检索离线评测；
- Evidence Verifier 反例测试。

### 22.2 Go

- Service 和 Repository 单元测试；
- Agent Client Mock 测试；
- 幂等创建任务测试；
- 鉴权和权限测试；
- Agent 状态同步集成测试。

### 22.3 前端

- 组件测试；
- API Mock 测试；
- 候选成分确认流程测试；
- 任务失败和重试交互测试；
- 结论—证据跳转测试；
- Playwright 端到端测试。

### 22.4 CI

每次合并运行：

- Go lint/test/build；
- Python lint/type-check/test；
- Frontend lint/test/build；
- OpenAPI 契约检查；
- 小规模 Agent Eval；
- Docker 镜像构建；
- Secret 扫描。

完整评测集可在定时任务或发布前运行，避免每次 PR 产生过高模型费用。

## 23. 简历与面试展示设计

### 23.1 项目名称建议

中文：中药超分子实验可验证多智能体科研平台  
英文：Verifiable Multi-Agent Platform for TCM Supramolecular Experiment Design

### 23.2 简历描述模板

以下表述需要在项目完成后填入真实指标：

- 设计并实现基于 React、Go、FastAPI 和 LangGraph 的跨语言科研 Agent 平台，支持状态持久化、失败恢复和 Human-in-the-loop；
- 基于 MCP 封装 PubChem、RDKit、文献检索和规则评分工具，实现工具协议与 Agent 编排解耦；
- 构建 Dense + Sparse + RRF + Cross-Encoder + 分子指纹的多阶段混合检索链路，并通过离线金标集验证检索提升；
- 设计 Chain-of-Evidence 机制，使形貌、条件和机理建议可追溯到文献片段、分子计算或规则结果；
- 基于 OpenTelemetry 与 Langfuse 打通 Go、Python、LLM 和工具调用链路，监控节点延迟、Token、成本和错误恢复；
- 建立中药超分子 Agent Benchmark，通过 DeepEval、Ragas 和人工评审评估工具调用、引用完整性和实验建议合理性。

### 23.3 面试重点问题

需要能够结合代码和数据回答：

1. 为什么选择 LangGraph，而不是 CrewAI 或 AutoGen？
2. MCP 与普通 Function Calling 有什么差异？
3. 为什么 Go 与 Python 分离，而不是全部改成 FastAPI？
4. 如何保证实验建议有证据而不是幻觉？
5. 如何评测没有唯一标准答案的科研 Agent？
6. Dense、Sparse、Reranker 和分子相似度如何融合？
7. Qdrant、Neo4j 和 MySQL 的边界是什么？
8. Agent 失败后怎样保证幂等和状态恢复？
9. 如何打通 Go/Python 的全链路 Trace？
10. 为什么生成模型和评审模型需要分离？

### 23.4 Demo Runbook

一次完整演示包括：

1. 用户输入“甘草、黄连”及研究目标；
2. 系统发现甘草酸、小檗碱等候选成分；
3. 用户查看结构图并确认成分；
4. LangGraph 恢复执行；
5. RDKit 计算分子特征和相似度；
6. 混合检索找到相关自组装文献；
7. Experiment Designer 生成候选条件；
8. Evidence Verifier 标记支持、部分支持和假设；
9. 用户审核并批准方案；
10. 页面展示方案、证据链和 Langfuse Trace；
11. 评测页展示相对 Baseline 的真实提升。

## 24. 主要风险与应对

| 风险 | 影响 | 应对措施 |
|---|---|---|
| 外部中药数据库接口不稳定 | 成分发现失败或数据不完整 | Provider Adapter、本地缓存、数据来源标记、人工补录 |
| 文献数据量少 | RAG 和 GraphRAG 增益有限 | 先做高质量金标和混合检索，再扩充 PDF |
| 化学名称和结构歧义 | 错误 SMILES 进入计算 | InChIKey 去重、来源交叉验证、人工确认 |
| LLM 生成无证据结论 | 科研可信度下降 | CoE、Verifier、HITL、禁止无证据事实进入最终方案 |
| Go/Python 状态不一致 | 任务重复或页面状态错误 | run_id、幂等键、MySQL 最终状态、节点幂等 |
| 技术组件过多 | 开发和运维成本上升 | 分阶段启用、Compose Profile、核心与增强能力分离 |
| 评测指标被模型自评污染 | 指标虚高 | 固定金标、生成/评审分离、人工抽检 |
| GraphRAG 没有实际增益 | 增加复杂度但无价值 | 只在 V4 Baseline 后建设，达不到指标则不进主链路 |
| 简历数字缺乏依据 | 面试风险 | 只使用真实 Benchmark 和 Trace 数据 |

## 25. 已确认的技术矩阵

### 25.1 核心必选

- React + TypeScript + Vite + Ant Design；
- Go + Gin + GORM；
- MySQL + Redis；
- Python + FastAPI；
- LangGraph；
- 五层 Memory Manager；
- Context Manager 与节点级 Token Budget；
- Skill Registry、Router 与 Runtime；
- Pydantic / PydanticAI；
- MCP；
- RDKit；
- Qdrant；
- BGE-M3 + BGE Reranker；
- Docling；
- Chain-of-Evidence；
- LiteLLM 或统一 Provider Adapter；
- OpenTelemetry + Langfuse；
- DeepEval + Ragas；
- Celery；
- Docker Compose。

### 25.2 第二阶段增强

- Neo4j GraphRAG；
- LlamaIndex PropertyGraphIndex；
- A2A；
- PDF 知识库；
- 多模型路由；
- CrewAI/AutoGen 对比实验；
- Prometheus + Grafana；
- SSE 实时任务进度；
- 实验反馈学习。

### 25.3 不进入主架构

- 多个 Agent 编排框架同时负责生产主流程；
- RocketMQ 在第一阶段即与同步 HTTP 调度并存；
- Kubernetes；
- Neo4j 和 Qdrant 重复保存同一向量并执行相同检索；
- 没有数据支撑的长期自主记忆；
- 没有人工审核的自动实验结论发布。

## 26. 开源参考项目

以下项目用于借鉴设计思想或集成，不代表全部进入主链路：

- LangGraph：https://github.com/langchain-ai/langgraph
- Model Context Protocol：https://github.com/modelcontextprotocol
- PydanticAI：https://github.com/pydantic/pydantic-ai
- GPT Researcher：https://github.com/assafelovic/gpt-researcher
- Microsoft AutoGen：https://github.com/microsoft/autogen
- CrewAI：https://github.com/crewAIInc/crewAI
- LlamaIndex：https://github.com/run-llama/llama_index
- Qdrant：https://github.com/qdrant/qdrant
- Neo4j：https://github.com/neo4j/neo4j
- Docling：https://github.com/docling-project/docling
- RDKit：https://github.com/rdkit/rdkit
- LiteLLM：https://github.com/BerriAI/litellm
- Langfuse：https://github.com/langfuse/langfuse
- OpenTelemetry：https://github.com/open-telemetry
- DeepEval：https://github.com/confident-ai/deepeval
- Ragas：https://github.com/explodinggradients/ragas

## 27. 五层记忆管理体系

### 27.1 设计目标

记忆系统负责跨节点、跨运行和跨项目保存必要信息，但不等同于保存全部聊天记录。平台采用五层记忆模型，并对每层定义独立作用域、存储位置、召回策略、保留周期和权限边界。

### 27.2 工作记忆 Working Memory

工作记忆服务于当前一次 Agent Run，由 LangGraph `AgentState` 与 Checkpoint 管理，保存当前研究目标、候选及已确认成分、分子计算结果、检索问题、证据、实验方案、人工审批状态、错误与重试信息。

工作记忆必须满足：

- 状态对象可序列化；
- 节点输入输出遵循 Pydantic Schema；
- 大文件和长文档只保存引用，不直接写入 Checkpoint；
- 支持暂停、恢复、节点重试和回放；
- 运行结束后生成结构化摘要，原始状态按审计策略保留。

### 27.3 情节记忆 Episodic Memory

情节记忆记录过去任务中发生过的事件，例如历史研究对象、Agent 初始建议、人工修改、审核原因、实验反馈、失败节点和恢复方式。

情节记忆保存到 MySQL，以 `user_id`、`project_id`、`run_id`、中药实体和成分实体建立索引。新任务开始时只召回与当前研究对象和目标相关的历史事件，不向模型注入全部运行历史。

### 27.4 语义记忆 Semantic Memory

语义记忆表示长期稳定的领域知识，包括中药、成分、文献、分子特征、组装形貌、实验条件、专家反馈及其关系。

- MySQL 保存结构化事实和事务数据；
- Qdrant 保存文献、实验记录和摘要向量；
- Neo4j 在第二阶段保存实体关系；
- 文件存储保存 Excel、PDF、结构图和报告；
- 所有记忆条目包含来源、版本、更新时间和可见范围。

### 27.5 程序记忆 Procedural Memory

程序记忆描述平台完成某类任务的方法，通过 Skill 表达，包括指令、工作流片段、MCP 工具绑定、输入输出 Schema、权限、示例和评测用例。

程序记忆不保存具体业务事实，而是保存“如何完成任务”。Skill 的修改采用版本化发布，并在离线评测通过后才能成为默认版本。

### 27.6 用户与项目记忆

用户记忆保存稳定偏好，例如可用仪器、默认溶剂、禁用试剂、输出语言和报告格式。项目记忆保存某一研究课题已经确认的成分、实验约束、假设和决策。

记忆作用域严格划分为：

```text
Global Memory   全平台公共知识
Project Memory  某个研究项目的长期上下文
User Memory     用户偏好和资源限制
Run Memory      当前任务状态
```

任何跨作用域召回都必须经过权限校验，禁止把一个用户或项目的私有实验数据注入另一个用户的上下文。

### 27.7 记忆写入与召回策略

记忆不是由 LLM 自由写入。写入流程包括候选提取、Schema 校验、敏感信息检查、去重、作用域确认和持久化。高价值科研结论必须经过人工确认后才能进入项目长期记忆。

召回采用以下顺序：

1. 根据当前用户、项目和实体做权限过滤；
2. 使用结构化条件缩小范围；
3. 使用语义与实体检索召回候选；
4. 根据时间、可信度和人工确认状态重排；
5. 交由 Context Manager 裁剪后进入模型上下文。

记忆必须支持失效、修订、删除、来源追踪和版本回滚，避免错误信息永久污染后续任务。

## 28. 上下文管理与 Context Engineering

### 28.1 Context Manager 职责

新增独立 Context Manager，在每个 LLM 节点执行前动态组装上下文。Context Manager 不负责业务推理，只负责选择、压缩、排序和格式化模型当前真正需要的信息。

上下文由以下内容组成：

```text
系统与安全指令
+ 当前 Skill 指令
+ 当前节点目标
+ LangGraph 工作状态
+ 项目与用户记忆
+ 检索到的文献证据
+ RDKit 与规则结果
+ 必要的近期对话
+ 输出 Schema
```

禁止默认采用“全部对话历史 + 全部文献 + 全部工具输出”的拼接方式。

### 28.2 上下文预算

Context Manager 为不同内容分配 Token Budget。初始建议比例为：系统与安全指令 10%、Skill 指令 10%、当前任务状态 15%、文献证据 35%、分子和规则结果 15%、必要对话历史 10%、输出空间预留 5%。

比例是初始配置，必须通过离线评测调整。不同节点使用不同预算模板，例如文献研究节点增加证据预算，结构化输出节点增加输出预留。

### 28.3 上下文压缩

平台同时维护：

- 原始记录：用于审计和回放，默认不进入模型；
- 结构化摘要：保存已确认事实、决策、证据 ID 和未解决问题；
- 当前窗口：只保存当前节点直接需要的消息和工具结果。

压缩过程必须保留 DOI、页码、Evidence ID、分子 ID、人工确认结果、不确定性和待解决问题。不得为了缩短上下文而丢失 Claim—Evidence 关联。

### 28.4 上下文组装策略

每个节点定义 `ContextPolicy`：

```python
class ContextPolicy(BaseModel):
    max_input_tokens: int
    reserved_output_tokens: int
    memory_scopes: list[str]
    evidence_top_k: int
    conversation_window: int
    require_citations: bool
    preserve_evidence_ids: bool
```

Context Manager 执行去重、相关性排序、来源多样性控制、Token 计算和超限裁剪。裁剪优先删除重复、低可信和与当前节点无关的内容。

### 28.5 Prompt Cache 与上下文安全

稳定的系统指令、Skill 指令和 Schema 可参与模型侧 Prompt Cache。用户输入、文献内容和工具结果按不可信数据处理，不允许覆盖系统指令或 Skill 权限。

上下文组装结果记录摘要哈希、策略版本和证据列表，便于在 Langfuse 中复现一次模型调用。

### 28.6 上下文评测指标

- 平均输入 Token 数；
- 有效证据利用率；
- 上下文重复率；
- 被截断证据比例；
- Claim—Evidence 保留率；
- 相同任务的成本和质量变化；
- 摘要后事实丢失率；
- 长对话中的任务一致性。

## 29. Skill Registry 与 Skill Runtime

### 29.1 Skill 定义

Skill 是可版本化的任务能力包，由元数据、触发条件、指令、工作流片段、MCP 工具绑定、输入输出 Schema、权限、上下文策略、示例和评测用例组成。

```text
Skill =
Metadata
+ Instructions
+ Workflow/Subgraph
+ MCP Tool Bindings
+ Input/Output Schema
+ Permissions
+ Context Policy
+ Examples
+ Evaluations
```

Skill 表达“如何完成任务”；MCP 表达“如何调用工具”；LangGraph 负责执行、状态和恢复；Context Manager 负责准备模型上下文；Memory 负责跨步骤与跨任务保存信息。

### 29.2 首批内置 Skill

- `compound-discovery`：发现、去重并校验候选成分；
- `molecular-analysis`：执行 SMILES 标准化、描述符和相似度计算；
- `literature-research`：拆解问题、混合检索并整理文献证据；
- `experiment-design`：生成形貌假设和实验条件矩阵；
- `evidence-verification`：核查结论、引用与不确定性；
- `proposal-review`：执行实验方案审核规则。

### 29.3 Skill 包结构

```text
agent/skills/
├── compound-discovery/
│   ├── skill.yaml
│   ├── instructions.md
│   ├── input.schema.json
│   ├── output.schema.json
│   ├── workflow.py
│   ├── examples/
│   └── evals/
├── molecular-analysis/
├── literature-research/
├── experiment-design/
└── evidence-verification/
```

`skill.yaml` 至少包含名称、版本、说明、触发条件、工具依赖、权限、Context Policy、输入输出 Schema 和兼容的工作流版本。

### 29.4 Skill Registry

Skill Registry 负责：

- Skill 注册、发现和版本查询；
- 启用、禁用和默认版本管理；
- 依赖和兼容性检查；
- 权限、网络和文件访问声明；
- 评测结果和发布状态；
- Skill 使用量、成功率和成本统计。

第一阶段使用 Git 管理 Skill 包、MySQL 保存注册元数据。后续如需第三方 Skill，再增加签名验证、来源信任和沙箱机制。

### 29.5 Skill Runtime

运行流程如下：

```text
用户意图
  -> Skill Router 选择候选 Skill
  -> 权限与版本检查
  -> 加载 Instructions、Schema 与 Context Policy
  -> Context Manager 组装上下文
  -> LangGraph 执行 Skill 子图
  -> Skill 调用 MCP Tools
  -> 输出 Schema 与业务规则校验
  -> Evidence 绑定
  -> 记录评测和 Trace
```

高风险 Skill 不允许自动运行，必须经过人工确认。Skill Router 的选择结果和理由进入 Trace，便于排查错误路由。

### 29.6 Skill 测试与发布

每个 Skill 必须具备：

- 输入输出契约测试；
- MCP 依赖 Mock；
- 正常、边界和拒绝案例；
- 固定离线评测集；
- Token、延迟和成功率基线；
- 权限测试；
- 版本升级和回滚测试。

Skill 发布状态分为 `draft`、`evaluation`、`active` 和 `deprecated`。只有通过评测阈值并完成代码审查的版本才能进入 `active`。

## 30. 最终结论

本项目采用“一个核心、三个亮点”的建设策略：

- 一个核心：LangGraph 可恢复科研工作流；
- 亮点一：MCP 标准化科学工具平台；
- 亮点二：RDKit + 混合检索 + GraphRAG + Chain-of-Evidence；
- 亮点三：OpenTelemetry + Langfuse + Benchmark 的 AgentOps 体系。

项目保持 60% Agent 系统工程与 40% 科研智能推理的比例。系统工程负责使平台可靠、可维护、可观测和可评测；科研智能负责形成中药超分子领域的差异化壁垒。所有前沿技术都必须服务于明确问题，并通过真实指标证明价值，避免成为开源组件陈列项目。
