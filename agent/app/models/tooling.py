from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

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

    herbs: list[str] = Field(min_length=1)


class NormalizeHerbsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    normalized_herbs: list[str]


class SearchMedicalKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=200)
    types: list[str] = Field(default_factory=list, max_length=6)
    limit: int = Field(default=10, ge=1, le=50)


class SearchMedicalKnowledgeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[dict[str, Any]] = Field(default_factory=list)
