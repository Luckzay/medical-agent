from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.models.tooling import (
    NormalizeHerbsInput,
    NormalizeHerbsOutput,
    RetryPolicy,
    SearchMedicalKnowledgeInput,
    SearchMedicalKnowledgeOutput,
    ToolDefinition,
)
from app.services.knowledge.retrieval.toxicology import search_toxicology
from app.services.knowledge.storage.embedding import DeterministicTestEmbedding
from app.services.knowledge.storage.factory import VectorRuntime, get_vector_runtime
from app.services.knowledge.storage.mysql_repository import MySQLCanonicalRepository
from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TOOL_VERSION = "1.4.0"
INTERNAL_TOOL_PERMISSIONS = frozenset({"herbs:normalize", "knowledge:search"})
MCP_TOOL_PERMISSIONS = INTERNAL_TOOL_PERMISSIONS


class HerbNormalizer(Protocol):
    def normalize(self, herbs: list[str]) -> list[str]: ...


def build_tool_registry(analysis: HerbNormalizer) -> ToolRegistry:
    registry = ToolRegistry()
    settings = get_settings()

    def normalize(request: NormalizeHerbsInput) -> NormalizeHerbsOutput:
        return NormalizeHerbsOutput(normalized_herbs=analysis.normalize(request.herbs))

    def search_medical_knowledge(
        request: SearchMedicalKnowledgeInput,
    ) -> SearchMedicalKnowledgeOutput:
        response = httpx.post(
            settings.knowledge_api_url,
            json=request.model_dump(mode="json"),
            headers={"X-Agent-Token": settings.internal_token},
            timeout=settings.knowledge_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            payload = {"results": payload}
        return SearchMedicalKnowledgeOutput.model_validate(payload)

    def search_toxicology_knowledge(
        request: SearchMedicalKnowledgeInput,
    ) -> SearchMedicalKnowledgeOutput:
        # Keep construction here so tests and deployments can inject both durable stores.
        repository = MySQLCanonicalRepository()
        try:
            vector_runtime = get_vector_runtime()
        except Exception as exc:
            logger.warning(
                "Qdrant runtime unavailable; continuing lexical-only: %s", type(exc).__name__
            )
            dimension = getattr(settings, "embedding_dimension", 8)
            vector_runtime = VectorRuntime(
                DeterministicTestEmbedding(dimension if isinstance(dimension, int) else 8),
                None,
                None,
            )
        return search_toxicology(
            request,
            settings,
            repository=repository,
            vector_runtime=vector_runtime,
        )

    registry.register_tool(
        ToolDefinition[NormalizeHerbsInput, NormalizeHerbsOutput](
            name="normalize_herbs",
            version=TOOL_VERSION,
            description="标准化、去重中药材名称。",
            input_model=NormalizeHerbsInput,
            output_model=NormalizeHerbsOutput,
            required_permissions=frozenset({"herbs:normalize"}),
            handler=normalize,
        )
    )
    registry.register_tool(
        ToolDefinition[SearchMedicalKnowledgeInput, SearchMedicalKnowledgeOutput](
            name="search_medical_knowledge",
            version=TOOL_VERSION,
            description="检索业务数据库中的医学知识，返回可引用的只读检索结果。",
            input_model=SearchMedicalKnowledgeInput,
            output_model=SearchMedicalKnowledgeOutput,
            required_permissions=frozenset({"knowledge:search"}),
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_retries=1),
            handler=search_medical_knowledge,
        )
    )
    registry.register_tool(
        ToolDefinition[SearchMedicalKnowledgeInput, SearchMedicalKnowledgeOutput](
            name="search_toxicology_knowledge",
            version=TOOL_VERSION,
            description=(
                "检索毒理知识库中的中药毒理记录，返回可公开展示的毒性字段、"
                "有毒成分及依据链接；不返回内部标识或数据源路径。"
            ),
            input_model=SearchMedicalKnowledgeInput,
            output_model=SearchMedicalKnowledgeOutput,
            required_permissions=frozenset({"knowledge:search"}),
            timeout_seconds=settings.toxicology_tool_timeout_seconds,
            retry_policy=RetryPolicy(max_retries=0),
            handler=search_toxicology_knowledge,
        )
    )
    return registry
