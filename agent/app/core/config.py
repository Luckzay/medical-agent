from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "medical-agent"
    service_version: str = "0.8.0"
    internal_token: str = Field(min_length=16)
    offline_mode: bool = True
    pubchem_timeout_seconds: float = Field(default=2.0, gt=0.0, le=10.0)
    database_path: Path = Path("./data/agent_runs.db")
    checkpoint_path: Path = Path("./data/checkpoints.db")
    evidence_source_path: Path = Path(
        "./resources/literature/TCM_Supramolecular_Literature_Search_EN_v3_filled.xlsx"
    )
    evidence_database_path: Path = Path("./data/evidence.db")
    canonical_database_path: Path = Path("./data/canonical_knowledge.db")
    evidence_tenant_id: str = Field(default="default", min_length=1, max_length=128)
    evidence_project_id: str = Field(default="literature", min_length=1, max_length=128)
    evidence_top_k: int = Field(default=10, ge=1, le=100)
    proposal_max_conditions: int = Field(default=12, ge=1, le=100)
    worker_count: int = Field(default=2, ge=1, le=64)
    vector_mode: Literal["disabled", "optional", "required"] = "disabled"
    llm_mode: Literal["disabled", "optional", "required"] = "disabled"
    llm_proxy_url: str = "http://127.0.0.1:8080/internal/v1/llm/chat"
    llm_timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    llm_stream_mode: Literal["optional", "required"] = "optional"
    knowledge_api_url: str = "http://127.0.0.1:8080/internal/v1/knowledge/search"
    knowledge_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    chat_max_agent_rounds: int = Field(default=8, ge=1, le=32)
    chat_max_tool_calls: int = Field(default=12, ge=1, le=64)
    chat_event_payload_chars: int = Field(default=4000, ge=256, le=32768)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection_alias: str = Field(
        default="medical_evidence_active", pattern=r"^[a-zA-Z0-9_-]+$"
    )
    supramolecular_collection: str = Field(
        default="supramolecular_experiments_active", pattern=r"^[a-zA-Z0-9_-]+$"
    )
    supramolecular_candidate_multiplier: int = Field(default=5, ge=1, le=20)
    qdrant_timeout_seconds: float = Field(default=5.0, gt=0.0, le=120.0)
    embedding_provider: Literal["sentence_transformers", "deterministic_test"] = (
        "sentence_transformers"
    )
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    embedding_dimension: int = Field(default=384, gt=0, le=65536)
    embedding_normalize: bool = True
    embedding_device: str = "cpu"
    embedding_max_seq_length: int = Field(default=512, ge=32, le=8192)
    embedding_batch_size: int = Field(default=16, ge=1, le=1024)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    embedding_retries: int = Field(default=2, ge=0, le=10)
    chunk_token_budget: int = Field(default=480, ge=32, le=10000)
    chunk_token_overlap: int = Field(default=64, ge=0, le=5000)
    chunker_version: str = "structure-first-v1"
    lexical_candidate_limit: int = Field(default=100, ge=1, le=1000)
    vector_candidate_limit: int = Field(default=100, ge=1, le=1000)
    fusion_rrf_k: int = Field(default=60, ge=1, le=1000)
    fusion_policy_version: str = "rrf-v1"
    reranker_mode: Literal["disabled", "optional", "required"] = "disabled"
    reranker_provider: Literal["disabled", "deterministic_test", "cross_encoder"] = "disabled"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_revision: str = "main"
    reranker_device: str = "cpu"
    reranker_batch_size: int = Field(default=8, ge=1, le=256)
    reranker_candidate_limit: int = Field(default=50, ge=1, le=1000)
    ingestion_batch_size: int = Field(default=32, ge=1, le=1024)
    ingestion_worker_limit: int = Field(default=2, ge=1, le=64)

    @model_validator(mode="after")
    def validate_vector_configuration(self) -> "Settings":
        if self.chunk_token_overlap >= self.chunk_token_budget:
            raise ValueError("chunk_token_overlap must be smaller than chunk_token_budget")
        if self.vector_mode == "required" and not self.qdrant_url:
            raise ValueError("qdrant_url is required in required vector mode")
        if self.embedding_provider == "deterministic_test" and self.vector_mode == "required":
            raise ValueError("deterministic_test embeddings cannot be used in required mode")
        if self.reranker_mode != "disabled" and self.reranker_provider == "disabled":
            raise ValueError("enabled reranker mode requires a reranker provider")
        if self.reranker_mode == "disabled" and self.reranker_provider != "disabled":
            raise ValueError("reranker provider must be disabled when reranker mode is disabled")
        return self

    @property
    def embedding_fingerprint(self) -> str:
        normalized = "l2" if self.embedding_normalize else "none"
        return (
            f"{self.embedding_provider}:{self.embedding_model}@{self.embedding_revision}:"
            f"d{self.embedding_dimension}:{normalized}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        extra="ignore",
    )

    def model_post_init(self, __context: Any) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_database_path.parent.mkdir(parents=True, exist_ok=True)
        self.canonical_database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
