from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge import ResponseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)
ToolHandler = Callable[[BaseModel], BaseModel]


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_retries: int = Field(default=0, ge=0, le=3)


class ToolDefinition[InputT: BaseModel, OutputT: BaseModel](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_model: type[InputT]
    output_model: type[OutputT]
    required_permissions: frozenset[str] = frozenset()
    timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    retry_policy: RetryPolicy = RetryPolicy()
    handler: Callable[[InputT], OutputT]

    def public_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "required_permissions": sorted(self.required_permissions),
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy.model_dump(mode="json"),
        }


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tool_names: tuple[str, ...] = Field(min_length=1)
    context_policy: dict[str, Any]


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    node: str = Field(min_length=1)
    permissions: frozenset[str]


class ToolAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str
    run_id: str
    node: str
    tool_name: str
    tool_version: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: str
    attempts: int
    error_type: str | None = None
    error_message: str | None = None


class NormalizeHerbsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    herbs: list[str] = Field(
        min_length=1, description="待标准化的药材名称列表", examples=[["大黄", "川大黄"]]
    )


class NormalizeHerbsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    normalized_herbs: list[str] = Field(description="标准化后的药材官方名称列表")


class SearchMedicalKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(
        min_length=1, max_length=200, description="检索查询关键词", examples=["大黄毒性"]
    )
    types: list[str] = Field(default_factory=list, max_length=6, description="检索类型过滤")
    limit: int = Field(default=5, ge=1, le=50, description="返回结果数量限制")


class SearchMedicalKnowledgeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[dict[str, Any]] = Field(default_factory=list, description="检索到的知识记录列表")


class ToolMetadataResponse(ResponseModel):
    name: str = Field(description="工具名称")
    version: str = Field(description="工具版本")
    description: str = Field(description="工具描述说明")
    input_schema: dict[str, Any] = Field(description="输入参数的 JSON Schema")
    output_schema: dict[str, Any] = Field(description="输出结果的 JSON Schema")
    required_permissions: list[str] = Field(description="执行该工具所需的权限列表")
    timeout_seconds: float = Field(description="工具执行超时时间（秒）")
    retry_policy: dict[str, Any] = Field(description="重试策略配置")


class SkillResponse(ResponseModel):
    name: str = Field(description="技能名称")
    version: str = Field(description="技能版本")
    description: str = Field(description="技能描述说明")
    tool_names: list[str] = Field(description="该技能包含的工具名称列表")
    context_policy: dict[str, Any] = Field(description="技能上下文策略配置")
