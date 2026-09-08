from __future__ import annotations

import sys

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models.knowledge import BlockType, NormalizedBlock, SourceLocator
from app.services.knowledge_ports import DocumentParser


def settings(**values: object) -> Settings:
    return Settings(internal_token="x" * 16, **values)  # type: ignore[arg-type]


def test_vector_defaults_are_offline_safe_and_embedding_is_optional() -> None:
    configured = settings()
    assert configured.vector_mode == "disabled"
    assert configured.embedding_fingerprint.endswith(":d384:l2")
    assert "sentence_transformers" not in sys.modules


def test_settings_reject_overlap_and_test_provider_in_required_mode() -> None:
    with pytest.raises(ValidationError, match="overlap"):
        settings(chunk_token_budget=100, chunk_token_overlap=100)
    with pytest.raises(ValidationError, match="deterministic_test"):
        settings(vector_mode="required", embedding_provider="deterministic_test")


def test_canonical_models_are_strict_and_protocol_is_vendor_neutral() -> None:
    block = NormalizedBlock(
        block_id="b1",
        version_id="v1",
        ordinal=0,
        block_type=BlockType.PARAGRAPH,
        text="content",
        locator=SourceLocator(source_uri="memory:test", start_line=1, end_line=1),
    )
    assert block.block_type is BlockType.PARAGRAPH
    assert "qdrant" not in str(DocumentParser.__annotations__).lower()
    with pytest.raises(ValidationError):
        NormalizedBlock.model_validate({**block.model_dump(), "vendor": "qdrant"})
