from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.models.knowledge import (
    BlockType,
    DocumentChunk,
    NormalizedBlock,
    OwnershipScope,
    SourceLocator,
)
from app.services.evidence_importer import import_literature
from app.services.knowledge_ports import DocumentParser, UnsupportedMediaTypeError


class ParserRegistry:
    def __init__(self, parsers: Sequence[DocumentParser] = ()) -> None:
        self._parsers: dict[str, DocumentParser] = {}
        for parser in parsers:
            self.register(parser)

    def register(self, parser: DocumentParser) -> None:
        for media_type in parser.media_types:
            self._parsers[media_type.lower()] = parser

    def get(self, media_type: str) -> DocumentParser:
        try:
            return self._parsers[media_type.lower().split(";", 1)[0].strip()]
        except KeyError as exc:
            raise UnsupportedMediaTypeError(media_type) from exc

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            "|".join(sorted(parser.fingerprint for parser in set(self._parsers.values()))).encode()
        ).hexdigest()


class PlainTextParser:
    media_types = frozenset({"text/plain"})
    fingerprint = "plain-text:v1:utf8-lines"

    def parse(self, content: bytes, version_id: str, source_uri: str) -> list[NormalizedBlock]:
        text = content.decode("utf-8-sig")
        blocks: list[NormalizedBlock] = []
        for ordinal, match in enumerate(re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, re.S)):
            value = match.group().strip()
            start = text[: match.start()].count("\n") + 1
            end = start + value.count("\n")
            blocks.append(
                _block(
                    version_id,
                    ordinal,
                    BlockType.PARAGRAPH,
                    value,
                    SourceLocator(source_uri=source_uri, start_line=start, end_line=end),
                )
            )
        return blocks


class MarkdownParser:
    media_types = frozenset({"text/markdown", "text/x-markdown"})
    fingerprint = "markdown:v1:headings-fences-tables"

    def parse(self, content: bytes, version_id: str, source_uri: str) -> list[NormalizedBlock]:
        lines = content.decode("utf-8-sig").splitlines()
        blocks: list[NormalizedBlock] = []
        headings: list[str] = []
        buffer: list[str] = []
        start = 1

        def flush(end: int) -> None:
            nonlocal buffer, start
            text = "\n".join(buffer).strip()
            if text:
                kind = BlockType.TABLE if "|" in text and "---" in text else BlockType.PARAGRAPH
                blocks.append(
                    _block(
                        version_id,
                        len(blocks),
                        kind,
                        text,
                        SourceLocator(
                            source_uri=source_uri,
                            start_line=start,
                            end_line=end,
                            heading_path=tuple(headings),
                        ),
                        tuple(headings),
                    )
                )
            buffer = []

        for line_number, line in enumerate(lines, 1):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                flush(line_number - 1)
                level, title = len(match.group(1)), match.group(2)
                headings[level - 1 :] = [title]
                blocks.append(
                    _block(
                        version_id,
                        len(blocks),
                        BlockType.HEADING,
                        title,
                        SourceLocator(
                            source_uri=source_uri,
                            start_line=line_number,
                            end_line=line_number,
                            heading_path=tuple(headings),
                        ),
                        tuple(headings),
                    )
                )
                start = line_number + 1
            elif not line.strip():
                flush(line_number - 1)
                start = line_number + 1
            else:
                if not buffer:
                    start = line_number
                buffer.append(line)
        flush(len(lines))
        return blocks


def _block(
    version_id: str,
    ordinal: int,
    kind: BlockType,
    text: str,
    locator: SourceLocator,
    hierarchy: tuple[str, ...] = (),
    metadata: dict[str, object] | None = None,
) -> NormalizedBlock:
    identity = uuid5(NAMESPACE_URL, f"{version_id}|{ordinal}|{kind}|{text}")
    return NormalizedBlock(
        block_id=str(identity),
        version_id=version_id,
        ordinal=ordinal,
        block_type=kind,
        text=text,
        locator=locator,
        hierarchy=hierarchy,
        metadata=metadata or {},
    )


def literature_blocks(
    path: str | Path, version_id: str
) -> tuple[list[NormalizedBlock], dict[str, str]]:
    records, _ = import_literature(path)
    blocks: list[NormalizedBlock] = []
    evidence: dict[str, str] = {}
    for ordinal, record in enumerate(records):
        data = record.model_dump(
            mode="json", exclude={"document_id", "source_file", "sheet", "source_row"}
        )
        text = "\n".join(
            f"{key}: {value}" for key, value in data.items() if value not in (None, [], "")
        )
        locator = SourceLocator(
            source_uri=record.source_file, sheet=record.sheet, row=record.source_row
        )
        block = _block(
            version_id,
            ordinal,
            BlockType.STRUCTURED_ROW,
            text,
            locator,
            metadata={
                "headers": list(data),
                "legacy_evidence_id": f"literature:{record.document_id}",
            },
        )
        blocks.append(block)
        evidence[f"literature:{record.document_id}"] = block.block_id
    return blocks, evidence


@dataclass(frozen=True)
class ChunkingPolicy:
    token_budget: int = 700
    overlap: int = 100
    version: str = "structure-first-v1"

    def __post_init__(self) -> None:
        if self.token_budget < 1 or self.overlap < 0 or self.overlap >= self.token_budget:
            raise ValueError("invalid chunking policy")

    @property
    def fingerprint(self) -> str:
        return f"{self.version}:tokens={self.token_budget}:overlap={self.overlap}"


class StructureFirstChunker:
    def __init__(self, policy: ChunkingPolicy | None = None) -> None:
        self.policy = policy or ChunkingPolicy()

    @property
    def fingerprint(self) -> str:
        return self.policy.fingerprint

    def chunk(
        self, blocks: Sequence[NormalizedBlock], scope: OwnershipScope
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        heading: str | None = None
        for block in blocks:
            if block.block_type is BlockType.HEADING:
                heading = block.text
                continue
            words = block.text.split()
            pieces = [words]
            if (
                block.block_type not in {BlockType.STRUCTURED_ROW, BlockType.TABLE}
                and len(words) > self.policy.token_budget
            ):
                step = self.policy.token_budget - self.policy.overlap
                pieces = [
                    words[index : index + self.policy.token_budget]
                    for index in range(0, len(words), step)
                ]
            for piece in pieces:
                text = " ".join(piece)
                context = " > ".join(block.hierarchy) or heading
                digest = hashlib.sha256(text.encode()).hexdigest()
                seed = "|".join(
                    (
                        scope.tenant_id,
                        scope.project_id,
                        block.version_id,
                        self.fingerprint,
                        block.locator.model_dump_json(),
                        digest,
                        str(len(chunks)),
                    )
                )
                chunks.append(
                    DocumentChunk(
                        chunk_id=str(uuid5(NAMESPACE_URL, seed)),
                        version_id=block.version_id,
                        scope=scope,
                        ordinal=len(chunks),
                        text=text,
                        content_hash=digest,
                        token_count=len(piece),
                        chunker_fingerprint=self.fingerprint,
                        locator=block.locator,
                        parent_context=context,
                        block_ids=(block.block_id,),
                    )
                )
        return chunks


class ChunkerRegistry:
    def __init__(self) -> None:
        self._chunkers: dict[str, StructureFirstChunker] = {}

    def register(self, name: str, chunker: StructureFirstChunker) -> None:
        self._chunkers[name] = chunker

    def get(self, name: str) -> StructureFirstChunker:
        try:
            return self._chunkers[name]
        except KeyError as exc:
            raise ValueError(f"unknown chunker: {name}") from exc
