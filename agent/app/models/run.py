from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.knowledge import RetrievalDiagnostics


def _to_rfc3339(value: datetime) -> str:
    """序列化为 Go time.Time 可解析的 RFC3339；naive 时间按 UTC 补齐。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LLMStatus(StrEnum):
    DISABLED = "disabled"
    GENERATED = "generated"
    DEGRADED = "degraded"


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, description="运行实例的唯一标识符", examples=["run_001"])
    user_id: int = Field(description="用户数字 ID", examples=[42])
    trace_id: str = Field(min_length=1, description="全链路追踪 ID", examples=["trace_999"])
    herbs: list[str] = Field(
        min_length=1, description="待分析的中药材列表", examples=[["大黄", "附子"]]
    )
    research_goal: str | None = Field(default=None, description="本次分析的研究目标说明")


class Evidence(BaseModel):
    evidence_id: str = Field(description="证据唯一标识符")
    source: str = Field(description="证据来源名称")
    source_type: str = Field(description="来源类型（如文献、数据库）")
    reference: str = Field(description="引用文献或记录的标识")
    retrieved_at: datetime | None = Field(default=None, description="检索时间")
    title: str | None = Field(default=None, description="证据标题")
    link: str | None = Field(default=None, description="来源链接")
    year: int | None = Field(default=None, description="发表年份")
    source_row: int | None = Field(default=None, description="原始数据行号")
    matched_fields: list[str] = Field(default_factory=list, description="匹配到的字段列表")
    score: float | None = Field(default=None, description="检索相关度评分")
    conditions: dict[str, str | None] | None = Field(default=None, description="检索过滤条件")
    document_id: str | None = Field(default=None, description="关联文档 ID")
    version_id: str | None = Field(default=None, description="关联版本 ID")
    chunk_id: str | None = Field(default=None, description="关联切片 ID")
    source_locator: dict[str, object] | None = Field(default=None, description="源定位元数据")
    retrieval_diagnostics: dict[str, object] | None = Field(
        default=None, description="检索诊断信息"
    )


class ClaimEvidence(BaseModel):
    claim_id: str = Field(description="断言 ID")
    claim_text: str = Field(description="断言具体文本内容")
    claim_type: str = Field(description="断言类型")
    evidence_ids: list[str] = Field(min_length=1, description="支持该断言的证据 ID 列表")
    confidence: float = Field(ge=0.0, le=1.0, description="断言置信度")
    basis: str = Field(description="得出该断言的依据逻辑")


class RuleHit(BaseModel):
    rule_id: str = Field(description="命中规则 ID")
    description: str = Field(description="规则描述")
    status: str = Field(description="命中状态")
    points: int = Field(description="规则分值")
    observed: str | float | int | None = Field(default=None, description="观测到的实际值")


class CandidateScore(BaseModel):
    rules: list[RuleHit] = Field(description="命中的具体规则列表")
    total_score: int = Field(description="总评分")
    candidate_threshold: int = Field(description="判定为候选的阈值")
    is_candidate: bool = Field(description="是否判定为有效候选")


class MolecularDescriptors(BaseModel):
    molecular_weight: float | None = Field(default=None, description="分子量")
    logp: float | None = Field(default=None, description="亲脂性系数")
    tpsa: float | None = Field(default=None, description="拓扑分子极性表面积")
    hbd: int | None = Field(default=None, description="氢键给体数")
    hba: int | None = Field(default=None, description="氢键受体数")


class CompoundResult(BaseModel):
    compound_id: str = Field(description="成分唯一标识符")
    name: str = Field(description="成分名称")
    herb: str = Field(description="关联药材名称")
    smiles: str | None = Field(default=None, description="SMILES 结构式")
    pubchem_cid: int | None = Field(default=None, description="PubChem CID")
    descriptors: MolecularDescriptors = Field(description="分子描述符")
    candidate_score: CandidateScore = Field(description="候选成分评分结果")
    evidence_ids: list[str] = Field(description="支持该成分分析的证据 ID 列表")


class AnalysisSummary(BaseModel):
    herb_count: int = Field(description="涉及药材总数")
    compound_count: int = Field(description="发现成分总数")
    candidate_count: int = Field(description="候选成分总数")
    unresolved_herbs: list[str] = Field(description="未能解析或检索到信息的药材列表")


class Capability(BaseModel):
    status: str = Field(description="能力状态")
    detail: str = Field(description="状态详情")


class WorkflowStep(BaseModel):
    node: str = Field(description="工作流节点名称")
    status: str = Field(description="执行状态")
    started_at: datetime = Field(description="开始时间")
    completed_at: datetime = Field(description="结束时间")
    detail: str = Field(description="执行详情")


class ToolingMetadata(BaseModel):
    skills: list[str] = Field(description="使用的技能列表")
    audit_ids: list[str] = Field(description="关联的工具审计日志 ID 列表")


class WorkflowMetadata(BaseModel):
    engine: str = Field(default="langgraph", description="工作流引擎类型")
    thread_id: str = Field(description="会话线程 ID")
    checkpoint_backend: str = Field(default="redis", description="状态持久化后端")
    status: WorkflowStatus = Field(description="工作流全局状态")
    steps: list[WorkflowStep] = Field(description="执行步骤列表")
    tooling: ToolingMetadata | None = Field(default=None, description="工具调用元数据")


class AnalysisResult(BaseModel):
    schema_version: str = Field(description="结果模式版本")
    normalized_herbs: list[str] = Field(description="归一化后的药材名称列表")
    compounds: list[CompoundResult] = Field(description="成分分析详细结果")
    summary: AnalysisSummary = Field(description="分析汇总摘要")
    capabilities: dict[str, Capability] = Field(description="服务能力状态映射")
    evidence: list[Evidence] = Field(description="引用的原始证据列表")
    claims: list[ClaimEvidence] = Field(default_factory=list, description="提取的断言及依据")
    workflow: WorkflowMetadata | None = Field(default=None, description="分析过程工作流元数据")
    retrieval_mode: str | None = Field(default=None, description="采用的检索模式")
    retrieval_diagnostics: list[RetrievalDiagnostics] = Field(
        default_factory=list, description="检索过程诊断日志"
    )
    llm_summary: str | None = Field(default=None, description="LLM 生成的分析综述")
    llm_status: LLMStatus = Field(default=LLMStatus.DISABLED, description="LLM 服务状态")


class RunResponse(RunCreate):
    status: RunStatus = Field(description="分析运行任务的当前状态")
    created_at: datetime = Field(description="任务创建时间")
    updated_at: datetime = Field(description="任务最后更新时间")

    @field_serializer("created_at", "updated_at")
    def _serialize_times(self, value: datetime) -> str:
        return _to_rfc3339(value)
    analysis_result: AnalysisResult | None = Field(
        default=None, description="分析任务产出的结果数据"
    )
    error_message: str | None = Field(default=None, description="任务执行失败时的错误原因")
    workflow: WorkflowMetadata | None = Field(default=None, description="工作流实时执行元数据")


class HealthResponse(BaseModel):
    service: str = Field(description="服务名称")
    status: str = Field(description="服务运行状态", examples=["ok"])
    version: str = Field(description="服务版本号")
