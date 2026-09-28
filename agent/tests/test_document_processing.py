from __future__ import annotations

import pytest

from app.models.knowledge import BlockType, OwnershipScope
from app.services.knowledge.core.ports import UnsupportedMediaTypeError
from app.services.knowledge.processing.documents import (
    ChunkingPolicy,
    MarkdownParser,
    ParserRegistry,
    PlainTextParser,
    StructureFirstChunker,
)


def test_registry_text_markdown_headings_positions_and_errors() -> None:
    registry = ParserRegistry([PlainTextParser(), MarkdownParser()])
    parsed = registry.get("text/markdown").parse(
        b"# Methods\n\npH 7.4 and 25 C\n\n| unit | value |\n|---|---|\n|nm|10|", "v1", "memory:md"
    )
    assert [block.block_type for block in parsed] == [
        BlockType.HEADING,
        BlockType.PARAGRAPH,
        BlockType.TABLE,
    ]
    assert parsed[1].hierarchy == ("Methods",)
    assert parsed[1].locator.start_line == 3
    assert parsed[2].metadata == {}
    with pytest.raises(UnsupportedMediaTypeError) as exc:
        registry.get("application/pdf")
    assert exc.value.media_type == "application/pdf"
    assert registry.fingerprint == ParserRegistry([MarkdownParser(), PlainTextParser()]).fingerprint


def test_chunker_is_structure_first_overlapping_and_deterministic() -> None:
    blocks = PlainTextParser().parse(
        (" ".join(f"w{i}" for i in range(20))).encode(), "v1", "memory:text"
    )
    scope = OwnershipScope(tenant_id="t", project_id="p")
    chunker = StructureFirstChunker(ChunkingPolicy(token_budget=10, overlap=3, version="test-v1"))
    first = chunker.chunk(blocks, scope)
    assert [item.token_count for item in first] == [10, 10, 6]
    assert first[0].text.split()[-3:] == first[1].text.split()[:3]
    assert first == chunker.chunk(blocks, scope)
    changed = StructureFirstChunker(
        ChunkingPolicy(token_budget=10, overlap=3, version="test-v2")
    ).chunk(blocks, scope)
    assert first[0].chunk_id != changed[0].chunk_id
