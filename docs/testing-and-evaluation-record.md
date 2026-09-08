# 测试与评测记录

> 更新时间：2026-08-09（CST）  
> 适用项目：中药超分子实验智能体平台  
> 维护原则：只记录能够由仓库文件、自动化测试输出或真实运行报告追溯的结果；弱标签、未运行模型和环境限制必须明确标注，不把工程可运行性等同于科研质量结论。

## 1. 文档目的与证据口径

本文集中记录项目迭代过程中已经执行的功能测试、质量门禁、数据迁移验证、向量索引验证、Agent 端到端验证和 RAG 检索评测，避免测试结论散落在 README、OpenSpec、JSON 报告和运行手册中。

本文中的结果分为三类：自动化测试结果、真实环境运行结果和弱标签评测结果。自动化测试用于验证代码行为与失败策略；真实环境运行用于验证 Qdrant、Embedding、LangGraph 等组件能够组成闭环；弱标签评测只用于建立可重复的工程基线，不能替代领域专家人工金标。

主要证据文件包括：

- `docs/real-migration-report.json`
- `docs/retrieval-baseline-v1.json`
- `docs/managed-vector-knowledge-base.md`
- `agent/reports/rag-baseline-real.md`
- `agent/reports/rag-baseline-real.json`
- `openspec/changes/archive/2026-08-09-connect-agent-online-hybrid-rag/e2e.md`
- `openspec/changes/evaluate-rag-and-add-reranker/`
- `agent/resources/evaluation/golden_retrieval_seed_v1.json`

## 2. 分阶段测试与验证记录

### 2.1 工作流、Skill 与 MCP 基础能力

Iteration 4 验证了异步工作流、LangGraph Checkpoint、运行状态持久化以及任务恢复相关能力。Iteration 5 验证了科研 Skill 注册、工具版本化、Tool Runtime 与 MCP 无状态 HTTP 接入。这些阶段的结论以项目 README、对应测试代码和后续累计回归测试为依据；目前仓库没有为这两个阶段保存独立的历史测试计数，因此本文不补写无法追溯的数字。

### 2.2 词法 Evidence RAG 与文献迁移

结构化文献数据来自：

`agent/resources/literature/TCM_Supramolecular_Literature_Search_EN_v3_filled.xlsx`

迁移和索引验证结果如下：

| 项目 | 结果 |
|---|---:|
| 原始结构化文献记录 | 131 |
| Structured Blocks | 131 |
| Canonical Chunks | 131 |
| Legacy Evidence Mappings | 131 |
| 迁移后记录一致性 | 通过 |

词法检索基于 SQLite FTS5/BM25，并结合结构化字段权重。迁移脚本入口为：

```bash
python -m app.scripts.migrate_literature
```

迁移证据见 `docs/real-migration-report.json`。当前 131 条结构化记录基本等价于“一条记录一个 chunk”，因此该阶段不能证明 PDF、Word 或超长全文的复杂分块效果。

### 2.3 托管向量知识库

向量知识库验证覆盖 canonical document/version/block/chunk 数据模型、摄取任务状态、Embedding Provider、Qdrant collection、alias 切换、回滚与 reconcile。

真实运行环境与结果如下：

| 项目 | 配置或结果 |
|---|---|
| Qdrant Server | 1.15.4 |
| Qdrant URL | `http://127.0.0.1:6333` |
| Collection | `medical_evidence_v20260809054053` |
| Active Alias | `medical_evidence_active` |
| Points | 131 |
| 向量名称 | `dense` |
| 距离函数 | Cosine |
| Embedding 模型 | `intfloat/multilingual-e5-small` |
| 模型 revision | `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| 向量维度 | 384 |
| Normalize | L2 normalize |
| 推理设备 | CPU |
| Batch size | 16 |
| Max sequence length | 512 |
| Query 前缀 | `query: ` |
| Passage 前缀 | `passage: ` |

真实服务验证包括 Qdrant `readyz`、服务版本、alias 指向、collection point count，以及容器重启后的持久化检查。结果确认 active alias 指向上述 collection，collection 中存在 131 个 points。

测试环境还使用内存 Qdrant 和 deterministic embedding 验证索引逻辑与失败路径。内存后端只用于自动化测试，不代表真实服务持久化结果；真实 131-point 结果来自 Qdrant Server。

### 2.4 在线 Hybrid RAG 与 Agent 端到端闭环

`search_literature`、LangGraph `evidence` 节点、Tool Runtime、MCP 和管理诊断接口已共享 Evidence Retrieval Service。在线链路能够执行 FTS5 词法召回、Qdrant 向量召回、RRF 融合、scope/version/lineage 校验和检索诊断输出。

归档 change `2026-08-09-connect-agent-online-hybrid-rag` 保存了一次真实七节点工作流验证。验证不是单独调用检索函数，而是执行完整的 `LangGraphAnalysisWorkflow.invoke`：

```text
normalize → discover → chemistry → evidence → proposal → review → finalize
```

端到端结果如下：

| 项目 | 结果 |
|---|---|
| 验证时间 | 2026-08-09 17:05 CST |
| 研究任务 | 当归阿魏酸超分子自组装机制与实验条件 |
| 工作流节点 | 7 |
| Retrieval mode | `hybrid` |
| 返回 Evidence | 10 条 |
| 总耗时 | 约 6.44 秒 |
| 检索耗时 | 约 6.36 秒 |
| Proposal 引用完整性 | 通过，引用均存在于最终 Evidence |
| Reviewer 结果 | `needs_revision` |

Reviewer 的 `needs_revision` 原因是实验条件和候选评分不足，不是引用缺失。这说明 Evidence 到 Proposal、Reviewer 的引用链路已打通，同时 Reviewer 没有因为流程成功而放弃质量约束。

完整证据见：

`openspec/changes/archive/2026-08-09-connect-agent-online-hybrid-rag/e2e.md`

### 2.5 RAG 自动评测与 Reranker

Iteration 10 新增了 Golden Dataset schema、严格校验、canonical hash、IR 指标、四模式 runner、参数网格、Embedding cache/generation 隔离，以及可插拔 Reranker Provider。

评测入口为：

```bash
python -m app.scripts.benchmark_rag
```

当前支持对比以下模式：

| 模式 | 状态 |
|---|---|
| Lexical only | 已运行 |
| Vector only | 已运行 |
| Hybrid RRF | 已运行 |
| Hybrid + real reranker | 框架已实现，真实模型未运行 |

Reranker 已接入在线 Evidence Retrieval 链路，并在 scope、active version 和 lineage 解析后执行。配置支持 `disabled`、`optional` 和 `required`：默认关闭时保持原排序；optional 失败时降级；required 失败时明确返回错误。测试 provider 和 lazy cross-encoder provider 已实现。

## 3. 真实 RAG Benchmark

### 3.1 数据集与运行参数

| 项目 | 值 |
|---|---|
| Corpus | 131 条结构化中药超分子文献记录 |
| Dataset | `golden_retrieval_seed_v1.json` |
| Query 数 | 6 |
| Query 语言 | 中文、英文 |
| 标签来源 | weak/synthetic seed |
| Dataset SHA-256 | `a9d60d5c283da5e75d2a649a70ac79851148da4b9c7d292c49c7b84cdc4c5576` |
| Collection generation | `20260809054053` |
| Embedding | `intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| Dimension | 384 |
| 随机种子 | 20260809 |

### 3.2 指标结果

| 模式 | Recall@10 | MRR@10 | nDCG@10 | 平均延迟 | P95 延迟 |
|---|---:|---:|---:|---:|---:|
| Lexical only | 1.0000 | 1.0000 | 1.0000 | 1.683 ms | 2.692 ms |
| Vector only | 1.0000 | 0.8667 | 0.8978 | 2456.301 ms | 14659.533 ms |
| Hybrid RRF | 1.0000 | 1.0000 | 1.0000 | 14.654 ms | 20.404 ms |
| Hybrid + real reranker | `not_run` | — | — | — | — |

完整报告见：

- `agent/reports/rag-baseline-real.md`
- `agent/reports/rag-baseline-real.json`

### 3.3 结果解释与限制

本次结果证明评测管线、真实 Qdrant/E5 检索和三种召回模式能够重复运行，但不能据此断言 RAG 已达到科研生产质量。

首先，当前只有 6 个 weak-label queries，标签由现有结构化数据构造，并非领域专家独立标注。Lexical 与 Hybrid 的满分很可能受到数据规模小、查询与结构化字段匹配度高等因素影响。

其次，Vector-only 的 P95 包含首次 E5 模型加载冷启动，因此不能当作稳定在线延迟。后续评测必须分别记录 cold start、warm cache、多轮均值和并发条件。

再次，当前 corpus 基本为单记录单 chunk，480-token budget 与 64-token overlap 尚未在真实长文档上形成有效对照实验。

最后，`BAAI/bge-m3` 和 `BAAI/bge-reranker-v2-m3` 均明确记录为 `not_run`。当前没有真实 reranker 收益数据，也没有把未执行配置写成评测结论。

## 4. 最新自动化质量门禁

Iteration 10 完成后的累计质量门禁结果如下：

| 门禁 | 最新结果 |
|---|---|
| Python pytest | 95 passed |
| Ruff | 通过 |
| strict mypy | 66 source files，无问题 |
| `uv lock --check` | 通过 |
| Go tests | 通过 |
| OpenAPI/YAML parse | 通过 |
| Iteration 10 OpenSpec strict validation | 通过 |
| 主 specs strict validation | 3/3 通过 |
| `git diff --check` | 通过 |

这里的 `95 passed` 是当前测试套件的累计结果，不应解释为每个历史 iteration 都单独运行过 95 个测试。历史阶段没有保存独立计数时，本文只记录“已被当前累计回归覆盖”，不反推历史数字。

重点自动化测试覆盖：

- 文档、版本、block、chunk 和 ingestion job 的 canonical 数据约束；
- parser/chunker/embedding/vector store 接口行为；
- collection、alias、rollback 和 reconcile；
- disabled/optional/required 向量检索模式；
- FTS5、vector 和 RRF 融合排序；
- scope、active version 和 lineage 安全；
- Recall、MRR、nDCG 与 graded relevance 计算；
- Dataset hash、可重复 runner 和 cache generation 隔离；
- Reranker lazy load、稳定排序、tie、非法分数与失败策略；
- Tool/MCP/OpenAPI 的 retrieval 与 rerank diagnostics。

## 5. 人工 Golden Dataset 的来源与建设方案

人工 Golden Dataset 不应直接从模型生成答案，也不应把当前 weak seed 改名后当作人工金标。它应由真实文献语料、真实科研问题和领域专家判断共同形成。

建议的数据来源包括项目现有 131 条结构化文献及其可追溯原文、后续依法接入的 PDF/Word/HTML 全文、课题组已有研究问题、实验方案检索问题、综述撰写问题，以及实际使用过程中匿名化并审核后的检索 query。每个 query 必须能够回到明确的文献版本与 chunk lineage。

双人复核流程建议如下：

1. 数据管理员从真实使用场景整理 query，覆盖实体检索、机制、实验条件、对比、否定证据、跨语言和无答案问题。
2. 专家 A 独立判断候选 chunk 的相关等级，推荐使用 0（不相关）、1（部分相关）、2（高度相关）、3（核心证据）。
3. 专家 B 在看不到专家 A 结果的情况下独立标注同一批数据。
4. 系统计算一致性，可采用 Cohen's kappa 或 weighted kappa，并列出全部冲突项。
5. 两位专家共同裁决冲突；无法达成一致的样本进入第三位专家或暂缓集。
6. 数据管理员冻结 dataset version、corpus generation、annotation guideline、专家角色、时间和 hash。
7. 评测只读取冻结版本，模型调参不得覆盖测试集标签。

建议首版人工集至少包含 50—100 个 query，并划分开发集和最终测试集。若资源有限，可先做 30 个高价值 query 验证流程，但不能据此给出最终上线质量结论。当前 6-query weak seed 可以作为候选问题和工具链示例，但必须由专家重新独立标注后才能进入人工 Golden Dataset。

## 6. 当前 RAG 完成度

按工程链路拆分，当前状态如下：

| 能力 | 状态 | 说明 |
|---|---|---|
| 结构化文献迁移 | 已完成 | 131 条已进入 canonical repository |
| 文档生命周期模型 | 已完成 | document/version/block/chunk/job/manifest 已具备 |
| FTS5/BM25 词法召回 | 已完成 | 在线可用 |
| Qdrant 向量索引 | 已完成 | 真实 Server、131 points、alias 已验证 |
| E5 Embedding | 已完成工程基线 | 固定 revision、384 维、CPU 可运行 |
| Hybrid RRF | 已完成 | Agent 在线链路已接通 |
| Evidence lineage/scope/version 校验 | 已完成 | 在 rerank 前执行 |
| Agent 七节点 RAG 闭环 | 已完成 | 已有真实 E2E 记录 |
| 检索诊断与失败降级 | 已完成 | disabled/optional/required |
| 自动评测框架 | 已完成 | 指标、hash、runner、cache 隔离已实现 |
| Reranker 软件框架 | 已完成 | provider、配置和失败策略已接入 |
| 真实 Cross-Encoder Reranker 评测 | 未完成 | 当前报告为 `not_run` |
| 多 Embedding 模型实测选型 | 未完成 | BGE-M3 等尚未运行 |
| 人工双人复核 Golden Dataset | 未完成 | 当前仅 weak seed |
| PDF/Word/HTML/OCR 全文摄取 | 未完成 | 当前主要是结构化 Excel 数据 |
| 长文档 tokenizer 精确切片评测 | 未完成 | 当前 chunker 仍有近似计数限制 |
| 生产级性能与容量验证 | 未完成 | 缺少 warm/concurrency/load benchmark |
| RAG 生成式 LLM 回答与答案质量评测 | 未完成 | 当前 Proposal/Reviewer 主要为确定性规则 |

因此，当前 RAG 已完成“可运行的工程闭环”，包括数据入库、双路召回、融合、引用追踪、Agent 消费、降级和自动评测框架；但还没有完成“科研生产质量闭环”，主要缺口是人工金标、真实模型横评、真实 reranker、多格式全文、长文档切片和生产负载验证。

## 7. 后续测试计划

下一阶段优先级建议为：先建立领域专家双人复核 Golden Dataset；再以固定 corpus generation 比较 E5、BGE-M3 等 Embedding；随后运行真实 Cross-Encoder Reranker，并分别统计质量收益与 warm latency；之后接入 PDF/Word/HTML/OCR 和 tokenizer 精确切片，重新进行 chunk 参数实验；最后补充并发、容量、故障恢复和在线回归监控。

每次新增 benchmark 时，应把原始 JSON 作为不可变证据保存，并在本文件中补充测试日期、代码版本或工作区标识、数据集 hash、corpus generation、模型 fingerprint、参数、硬件、冷暖状态、指标和限制。