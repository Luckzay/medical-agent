# Agent RAG 调用流程与内部运作说明

本文档面向项目开发者，详细说明 `agent/` 服务中一次 Agent Run 从接收请求到返回分析结果的完整链路，重点解释：

- RAG 在工作流中的触发位置
- 检索请求如何构造
- 词法检索、向量检索、融合、重排的具体处理方式
- 检索结果如何回流到工作流并参与后续 proposal/review/finalize
- Run 的持久化、恢复与审计机制
- 当前实现里哪些步骤是确定性逻辑，哪些步骤会发送给 LLM

## 1. 先说结论

当前 `agent` 服务的主链路是：

```text
Go backend 创建 Agent Run
  -> Python FastAPI 接收内部请求
  -> RunService 创建/调度任务
  -> LangGraph 工作流按节点执行
  -> evidence 节点触发 RAG 检索
  -> proposal/review/finalize 消费检索结果
  -> SQLite 持久化最终结果与 workflow 元数据
```

当前默认配置下，RAG 主要走：

```text
SQLite FTS5 词法检索
```

只有在 `AGENT_VECTOR_MODE=optional|required` 时，才会启用：

```text
Embedding -> Qdrant 向量检索 -> RRF 融合 -> 可选 Reranker
```

另外一个非常重要的事实是：

```text
当前这条主链路没有实际调用 LLM。
```

目前的 `normalize / discover / chemistry / evidence / proposal / review / finalize` 都是确定性逻辑、规则逻辑或检索逻辑，不是把上下文拼成 prompt 发给大模型生成答案。

## 2. 目录与关键文件

### 2.1 对外入口

- `agent/app/main.py`
- `agent/app/api/routes.py`

### 2.2 任务调度与工作流

- `agent/app/services/run_service.py`
- `agent/app/services/workflow.py`
- `agent/app/services/run_repository.py`

### 2.3 RAG 核心

- `agent/app/services/builtin_tools.py`
- `agent/app/services/evidence_retrieval.py`
- `agent/app/services/evidence_store.py`
- `agent/app/services/retrieval_query.py`
- `agent/app/services/hybrid_retrieval.py`
- `agent/app/services/runtime.py`
- `agent/app/services/embeddings.py`
- `agent/app/services/rerankers.py`
- `agent/app/services/vector_index.py`
- `agent/app/services/knowledge_repository.py`

### 2.4 工作流下游处理

- `agent/app/services/analysis_service.py`
- `agent/app/services/proposal_service.py`

## 3. 端到端总流程

一次标准调用的顺序如下：

```text
1. Go backend -> POST /internal/v1/runs
2. FastAPI route 调用 RunService.create()
3. RunService 在 agent_runs.db 中创建一条 running 记录
4. RunService 把任务提交给线程池
5. 后台线程执行 LangGraphAnalysisWorkflow.invoke()
6. 工作流依次执行：
   normalize
   -> discover
   -> chemistry
   -> evidence   <- RAG 从这里触发
   -> proposal
   -> review
   -> finalize
7. RunService 把 analysis_result、workflow、status 写回 SQLite
8. Go backend 通过 GET /internal/v1/runs/{run_id} 拉取结果
```

## 4. 请求是如何进入 Agent 的

上游 Go 服务会调用 Python Agent 的内部接口：

```text
POST /internal/v1/runs
```

请求模型定义在 `agent/app/models/run.py`：

```python
class RunCreate(BaseModel):
    run_id: str
    user_id: int
    trace_id: str
    herbs: list[str]
    research_goal: str | None
```

这是一次 Agent Run 的原始输入。典型请求体：

```json
{
  "run_id": "run_123",
  "user_id": 1,
  "trace_id": "trace_123",
  "herbs": ["黄芪", "当归"],
  "research_goal": "分析两味药的主要成分、潜在超分子候选以及相关文献证据"
}
```

路由层只做几件事：

1. 校验内部 token
2. 调用 `RunService.create()`
3. 把异常映射成 HTTP 状态码

真正的业务处理从 `RunService` 开始。

## 5. RunService：任务调度与生命周期管理

文件：

```text
agent/app/services/run_service.py
```

`RunService` 的职责不是分析本身，而是：

1. 创建 Run 记录
2. 管理线程池异步执行
3. 在完成/失败后更新状态
4. 支持 `resume`
5. 支持服务重启后的任务恢复

### 5.1 create 阶段

`RunService.create()` 会先调用 `SQLiteRunRepository.create()`，在 `agent_runs.db` 中创建一条 `running` 记录：

```text
status = RUNNING
analysis_result_json = NULL
workflow_json = NULL
error_message = NULL
```

然后 `_submit()` 把任务丢进线程池，后台调用 `_execute()`。

### 5.2 _execute 阶段

`_execute()` 会调用：

```python
self._workflow.invoke(run_id, herbs, research_goal)
```

如果执行成功：

```text
status -> COMPLETED
analysis_result_json -> 最终分析结果
workflow_json -> 节点执行元数据
```

如果执行异常：

```text
status -> FAILED
error_message -> 异常文本
workflow_json -> 失败节点的 workflow metadata
```

## 6. LangGraph 工作流：节点、状态与 checkpoint

文件：

```text
agent/app/services/workflow.py
```

### 6.1 工作流状态

共享状态 `WorkflowState` 是工作流内部的单一上下文对象，字段会随着节点推进逐步补全：

```python
class WorkflowState(TypedDict):
    herbs: list[str]
    research_goal: NotRequired[str | None]
    normalized_herbs: NotRequired[list[str]]
    discovered: NotRequired[list[dict[str, object]]]
    compounds: NotRequired[list[dict[str, object]]]
    evidence: NotRequired[list[dict[str, object]]]
    claims: NotRequired[list[dict[str, object]]]
    retrieval_mode: NotRequired[str]
    retrieval_diagnostics: NotRequired[list[dict[str, object]]]
    proposal: NotRequired[dict[str, object]]
    proposal_review: NotRequired[dict[str, object]]
    unresolved_herbs: NotRequired[list[str]]
    online_failures: NotRequired[int]
    analysis_result: NotRequired[dict[str, object]]
    steps: list[dict[str, object]]
```

### 6.2 节点顺序

当前图是固定线性图：

```text
START
  -> normalize
  -> discover
  -> chemistry
  -> evidence
  -> proposal
  -> review
  -> finalize
  -> END
```

### 6.3 checkpoint

工作流通过 `SqliteSaver` 使用 `run_id` 作为 `thread_id` 保存 checkpoint，因此：

- 服务重启后可恢复
- `resume(run_id)` 可以从 checkpoint 继续
- `workflow.metadata()` 能还原已完成节点和失败节点

## 7. 节点级详细流程

下面按节点说明每一步做了什么。

### 7.1 normalize

职责：

- 标准化药材名称
- 去重
- 别名归一

调用工具：

```text
normalize_herbs
```

工具实现最终落到：

```text
AnalysisService.normalize()
```

典型处理包括：

- 去掉前后空格
- Unicode 标准化
- 将别名映射为规范名称

例子：

```text
黃耆 -> 黄芪
炙甘草 -> 甘草
```

输出写回 `WorkflowState.normalized_herbs`。

### 7.2 discover

职责：

- 从本地确定性种子库发现候选成分
- 在允许时补全 PubChem 信息
- 生成初始 evidence 和 unresolved_herbs

调用工具：

```text
discover_compounds
```

工具实现最终落到：

```text
AnalysisService.discover()
```

主要处理方式：

1. 从本地种子库按药材名查候选成分
2. 如果启用在线补全，则查询 PubChem
3. 输出 `compound_id / name / herb / smiles / pubchem_cid / evidence_ids`

这里的成分发现仍然是确定性流程，不涉及 LLM。

### 7.3 chemistry

职责：

- 计算分子描述符
- 按固定规则进行候选评分

调用工具：

```text
calculate_descriptors
score_supramolecular_candidate
```

具体处理方式：

#### 7.3.1 calculate_descriptors

由 `AnalysisService.calculate_descriptors()` 驱动，内部使用 `DescriptorCalculator`。

如果 RDKit 可用，会计算：

- `molecular_weight`
- `logp`
- `tpsa`
- `hbd`
- `hba`

如果 RDKit 不可用，返回空描述符结构，而不是让整个流程失败。

#### 7.3.2 score_supramolecular_candidate

由 `AnalysisService.score()` 调用 `score_candidate()` 完成。

当前评分是规则化的，不是模型预测。检查项包括：

- 分子量区间
- logP 区间
- TPSA 区间
- HBD/HBA
- 是否存在环结构
- 是否包含 O/N/S 等杂原子

输出是结构化 `CandidateScore`：

- `rules`
- `total_score`
- `candidate_threshold`
- `is_candidate`

### 7.4 evidence：RAG 主入口

职责：

- 构造检索请求
- 调用 `search_literature`
- 把检索结果回填到 compounds/evidence/claims

这里是当前 Agent 中 RAG 的核心节点。

#### 7.4.1 evidence 节点传给检索工具的内容

`workflow.py` 中 evidence 节点会构造：

```python
{
    "query": state.get("research_goal"),
    "research_goal": state.get("research_goal"),
    "herbs": state["normalized_herbs"],
    "compounds": [item.name for item in compounds],
    "smiles": [item.smiles for item in compounds if item.smiles],
    "top_k": get_settings().evidence_top_k,
    "retrieval_mode": get_settings().vector_mode,
    "diagnostics": True,
}
```

这个请求同时融合了：

- 用户研究目标
- 规范药材名
- 已发现的化合物名
- 化学结构 SMILES

注意：

```text
这里不是把上下文拼成 prompt 发给 LLM，
而是构造结构化检索输入。
```

## 8. RAG 的内部实现

### 8.1 调用入口：search_literature 工具

工作流不会直接调用检索服务，而是先走：

```text
ToolRuntime.execute("search_literature")
```

工具由 `builtin_tools.py` 注册，最终调用：

```python
EvidenceRetrievalService.search(...)
```

这层的作用是统一提供：

- 输入输出 schema 校验
- 权限校验
- 超时与重试
- 审计日志

### 8.2 检索请求构造：retrieval_query.py

`build_retrieval_query()` 会生成两个版本的查询：

- `lexical`：给词法检索使用
- `vector`：给 embedding / 向量检索使用

处理逻辑：

1. 清洗 `query / research_goal / herbs / compounds / smiles`
2. 构造稳定的 lexical query
3. 构造更适合 E5 embedding 的 vector query
4. 从 lexical query 中识别 DOI
5. 从输入中保留 exact smiles

构造结果示例：

```text
lexical:
  分析两味药的主要成分 黄芪 当归 黄芪甲苷 阿魏酸 COC1...

vector:
  分析两味药的主要成分；中药：黄芪、当归；候选成分：黄芪甲苷、阿魏酸；SMILES：...
```

## 9. 第一层召回：SQLite FTS5 词法检索

文件：

```text
agent/app/services/evidence_store.py
```

### 9.1 文献索引来源

当前文献源来自 Excel，经 `EvidenceStore.ensure_index()` 导入 SQLite。

导入时会：

1. 读取原始文献结构化数据
2. 写入 `literature_records`
3. 建立 `literature_fts` 虚表
4. 保存 `source_hash` 和 `schema_version`

### 9.2 检索通道

词法检索不是只查全文，而是多个通道并行评分：

- `fts_bm25`
- `herb`
- `compound`
- `smiles`

具体含义：

- `fts_bm25`：对 `title/authors/herbs/compounds/mechanism/remarks` 等字段做 FTS5 检索
- `herb`：按标准化药材字段做 contains 匹配
- `compound`：按标准化成分字段做 contains 匹配
- `smiles`：按结构字符串做精确匹配

### 9.3 词法检索分数

当前加权公式是：

```text
final_score =
  0.45 * fts_bm25
  + 0.20 * herb
  + 0.20 * compound
  + 0.15 * smiles
```

输出结果为 `LiteratureSearchHit`，其中包含：

- 文档 ID
- 标题
- DOI/链接
- 命中的字段
- 每个通道的分数
- 最终分数
- 文献中记录的实验条件

### 9.4 默认模式

如果：

```text
AGENT_VECTOR_MODE=disabled
```

则检索在这里结束，直接返回词法检索结果。

这就是当前默认运行路径。

## 10. 第二层召回：向量检索

文件：

```text
agent/app/services/evidence_retrieval.py
agent/app/services/runtime.py
agent/app/services/embeddings.py
agent/app/services/vector_index.py
```

### 10.1 启用条件

只有在：

```text
AGENT_VECTOR_MODE=optional
```

或：

```text
AGENT_VECTOR_MODE=required
```

时，才会进入向量检索路径。

### 10.2 embedding provider

`runtime.py` 会根据配置构造 `VectorRuntime`。

- `disabled`：返回 `DeterministicTestEmbedding`，但不创建向量库连接
- `optional|required`：使用 `LazySentenceTransformerEmbedding`

`LazySentenceTransformerEmbedding` 的特点：

- 首次真正调用时才加载模型
- 支持重试
- 校验 embedding 维度
- 对 query 使用 `query: ...`
- 对文档使用 `passage: ...`

当前默认 embedding fingerprint 体现：

- 模型名
- revision
- 维度
- 是否归一化
- query 模板类型

### 10.3 向量库

运行时通过 `QdrantClient` 访问 Qdrant。

如果别名下已有 active collection，则直接使用。
如果没有 active manifest，会创建一个待使用的 manifest 结构，但不自动把数据变成可检索状态；真正的索引构建和 alias 管理由管理流程负责。

## 11. 混合检索：lexical + vector + RRF

文件：

```text
agent/app/services/hybrid_retrieval.py
```

### 11.1 输入

`HybridRetriever.search()` 接收：

- `query`：vector query
- `scope`：租户/项目范围
- `lexical_chunk_ids`：来自词法检索结果映射出的 chunk IDs
- `exact_boosts`：精确 DOI/SMILES 命中

### 11.2 向量召回

向量召回步骤：

1. `embedding.embed_query(query)`
2. `vector_store.search(...)`
3. 得到按相似度排序的 `vector_ids`

如果向量库不存在或 embedding 失败：

- `optional` 模式下允许降级
- `required` 模式下抛错

### 11.3 RRF 融合

当前融合算法是：

```text
Reciprocal Rank Fusion
```

公式思想是：

- 一个文档在 lexical 排得越靠前，得分越高
- 一个文档在 vector 排得越靠前，得分越高
- 同时出现在两边时，优势叠加

同时还会对 DOI/SMILES 等精确命中进行 boost。

### 11.4 血缘与权限过滤

RRF 之后不会立刻输出结果，而是先去 `knowledge_repository` 里解析 chunk：

- 校验 chunk 是否仍然有效
- 校验 canonical lineage
- 校验 ownership scope

也就是说：

```text
先做权限和文档血缘过滤，
再把 passage 交给后续 reranker。
```

### 11.5 reranker

如果 `reranker_mode != disabled`，会对候选 passage 再打一次分。

支持：

- `disabled`
- `deterministic_test`
- `cross_encoder`

当前 `cross_encoder` 通过 `sentence_transformers.CrossEncoder` 延迟加载。

如果 reranker 失败：

- `optional` 风格下保留 fused 顺序，并标记 `reranker_unavailable`
- `required` 风格下抛出 `RequiredRerankerError`

## 12. RAG 的降级策略

RAG 不是单一路径，而是有明确降级策略：

### 12.1 `vector_mode=disabled`

只走 lexical。

### 12.2 `vector_mode=optional`

优先尝试 hybrid，如果向量链路失败则退回 lexical。

返回中会标记：

- `degraded=True`
- `retrieval_mode="lexical"`
- `degraded_reason=...`

### 12.3 `vector_mode=required`

向量链路失败直接报错，不允许悄悄降级。

这是生产门禁模式。

## 13. 检索结果如何回流到工作流

evidence 节点拿到 `SearchLiteratureOutput` 后，会做三件事。

### 13.1 文献命中转为结构化 Evidence

每个 hit 会被转成 `Evidence`：

- `evidence_id = literature:{document_id}`
- 来源固定为文献数据集
- 保留标题、链接、年份、命中字段、得分、条件等信息

### 13.2 把文献绑定到 compounds

如果文献 hit 中：

- 出现了 compound 的 SMILES
- 或出现了 compound 名称

则将：

```text
compound.evidence_ids += evidence_id
```

这一步的作用是把“检索回来的文献”与“前面发现的化合物候选”建立引用关系。

### 13.3 生成 claims

对于已经绑定文献证据的 candidate compound，会生成 `ClaimEvidence`：

- `claim_id`
- `claim_text`
- `claim_type`
- `evidence_ids`
- `confidence`
- `basis`

这里特别注意：

```text
claim_text 说的是“确定性候选规则得分”，
不是“文献已经证明该成分有效”。
```

也就是说，文献是支持性证据，规则评分仍然是规则评分，不做概念混淆。

## 14. proposal：基于证据生成实验方案

文件：

```text
agent/app/services/proposal_service.py
```

`proposal` 节点消费：

- `compounds`
- `claims`
- `evidence`

生成 `ExperimentProposal`。

当前方案生成是确定性的，不是 LLM 输出。

主要处理方式：

1. 按 candidate_score 对 compounds 排序
2. 优先选择 `is_candidate=True` 的化合物
3. 每个候选必须绑定可用 evidence，否则报错
4. 从文献 conditions 中抽取条件矩阵
5. 如果没有文献条件，则生成探索性 baseline，并显式标记风险
6. 自动生成 measurement plan、blank control、risk items

输出中的每个 proposal 子项都尽量携带 `evidence_ids`。

## 15. review：独立审查 proposal

`review_experiment_proposal()` 同样是规则化审查，不是 LLM 审稿。

检查项包括：

- proposal 中引用的 `evidence_ids` 是否存在
- 文献支持标记与来源类型是否一致
- 条件矩阵是否完整
- 是否存在 blank 或 negative control
- 是否存在 measurement plan
- candidate score 信息是否完整
- 是否存在 exploratory defaults
- 安全声明、研究声明是否存在

输出是结构化 `ProposalReview`，不是自然语言长文。

## 16. finalize：汇总最终结果

`finalize` 节点会调用 `AnalysisService.finalize()`，把前面所有结果归并成：

```text
AnalysisResult
```

最终包含：

- `normalized_herbs`
- `compounds`
- `summary`
- `capabilities`
- `evidence`
- `claims`
- `proposal`
- `proposal_review`
- `workflow`
- `retrieval_mode`
- `retrieval_diagnostics`

其中 `workflow.tooling.audit_ids` 来自 `ToolRuntime` 的工具审计记录。

## 17. ToolRuntime：RAG 调用过程中的安全与审计层

文件：

```text
agent/app/services/tool_runtime.py
```

任何工具调用，包括 `search_literature`，都会先经过 `ToolRuntime`。

它提供：

1. 权限校验
2. 输入 schema 校验
3. handler 执行
4. 输出 schema 校验
5. 超时控制
6. retry
7. SQLite 审计落库

审计记录包含：

- run_id
- node
- tool_name
- tool_version
- started_at / completed_at
- duration_ms
- status
- attempts
- error_type / error_message

因此，RAG 检索虽然看起来只是一个工具调用，但实际上是：

```text
工作流节点
  -> 工具运行时
  -> 检索服务
  -> 检索链路
  -> 审计记录
```

## 18. 持久化与恢复机制

### 18.1 Run 持久化

`run_repository.py` 使用 SQLite 保存：

- `run_id`
- `user_id`
- `trace_id`
- `herbs_json`
- `research_goal`
- `status`
- `analysis_result_json`
- `workflow_json`
- `error_message`
- `created_at / updated_at`

### 18.2 Workflow checkpoint

LangGraph 使用独立的 checkpoint SQLite 保存节点执行进度。

### 18.3 服务重启恢复

FastAPI lifespan 启动时会执行：

```python
run_service.recover_running_tasks()
```

它会把数据库里仍处于 `RUNNING` 的任务重新加入线程池，并根据是否存在 checkpoint 决定：

- 从头 invoke
- 或从 checkpoint resume

## 19. 当前链路中，哪些内容发送给了 LLM

当前实现下，主链路中没有实际 LLM 调用。

### 19.1 当前发送的是这些结构化请求

- `normalize_herbs`
- `discover_compounds`
- `calculate_descriptors`
- `score_supramolecular_candidate`
- `search_literature`
- `generate_experiment_proposal`
- `review_experiment_proposal`

这些调用的底层是：

- Python 规则
- SQLite 检索
- 可选 Qdrant 向量检索
- 可选 RDKit
- 可选 PubChem
- 结构化 proposal/review 逻辑

### 19.2 当前没有这些行为

当前主路径中没有：

- 把 system/user prompt 发给聊天模型
- 让 LLM 自由决定下一步工具
- 让 LLM 生成最终长文本答案
- 让 LLM 审稿或做证据校验

因此严格来说，当前实现是：

```text
LangGraph 编排的确定性科研工作流
+ 可配置 RAG 检索链路
```

而不是“对话式大模型 Agent 主导的自由推理流程”。

## 20. 一次典型运行的时序摘要

```text
用户输入 herbs + research_goal
  -> Go backend 创建 run_id
  -> Python /internal/v1/runs
  -> RunService.create
  -> SQLiteRunRepository.create(status=running)
  -> LangGraph.invoke
      -> normalize
      -> discover
      -> chemistry
      -> evidence
          -> ToolRuntime.execute(search_literature)
          -> build_retrieval_query
          -> lexical search
          -> optional vector search
          -> optional rerank
          -> 返回 hits
          -> 回填 evidence_ids / claims
      -> proposal
      -> review
      -> finalize
  -> RunService.update(status=completed)
  -> Go backend 拉取结果
```

## 21. 最后用一句话概括

当前 Agent 的 RAG 链路本质上是：

```text
工作流 evidence 节点基于研究目标、药材、化合物和 SMILES 构造结构化检索请求，
先走 SQLite FTS5 词法召回，再按配置选择是否叠加 Embedding + Qdrant 向量召回、
RRF 融合和可选 reranker，最后把命中文献绑定回候选化合物与 claims，
供后续 proposal/review/finalize 使用。
```

它的内部运作核心不是“让 LLM 回答问题”，而是：

```text
确定性工作流 + 可配置混合检索 + 结构化实验设计与审查 + 持久化恢复
```
