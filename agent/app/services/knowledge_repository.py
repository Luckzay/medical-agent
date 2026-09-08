# ruff: noqa: E501
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models.knowledge import (
    CanonicalDocument,
    DocumentChunk,
    DocumentStatus,
    DocumentVersion,
    IndexManifest,
    IngestionJob,
    NormalizedBlock,
    OwnershipScope,
    SourceLocator,
)


class ImmutableVersionError(ValueError):
    pass


_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_migrations VALUES(1);
CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,logical_source TEXT NOT NULL,media_type TEXT NOT NULL,status TEXT NOT NULL,active_version_id TEXT,created_at TEXT NOT NULL,tombstoned_at TEXT,UNIQUE(tenant_id,project_id,logical_source));
CREATE TABLE IF NOT EXISTS document_versions(version_id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(document_id),tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,source_hash TEXT NOT NULL,source_locator_json TEXT NOT NULL,media_type TEXT NOT NULL,parser_fingerprint TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(document_id,source_hash));
CREATE TABLE IF NOT EXISTS document_blocks(block_id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES document_versions(version_id),tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,ordinal INTEGER NOT NULL,payload_json TEXT NOT NULL,UNIQUE(version_id,ordinal));
CREATE TABLE IF NOT EXISTS document_chunks(chunk_id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES document_versions(version_id),tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,ordinal INTEGER NOT NULL,content_hash TEXT NOT NULL,payload_json TEXT NOT NULL,UNIQUE(version_id,ordinal));
CREATE TABLE IF NOT EXISTS ingestion_jobs(job_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,document_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,stage TEXT NOT NULL,payload_json TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(tenant_id,project_id,idempotency_key));
CREATE TABLE IF NOT EXISTS embedding_cache(content_hash TEXT NOT NULL,embedding_fingerprint TEXT NOT NULL,dimension INTEGER NOT NULL,vector_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(content_hash,embedding_fingerprint));
CREATE TABLE IF NOT EXISTS index_manifests(manifest_id TEXT PRIMARY KEY,collection_name TEXT NOT NULL UNIQUE,alias TEXT NOT NULL,generation TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS legacy_evidence_mappings(evidence_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,document_id TEXT NOT NULL,version_id TEXT NOT NULL,chunk_id TEXT NOT NULL,source_row INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_versions_scope ON document_versions(tenant_id,project_id,document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_scope ON document_chunks(tenant_id,project_id,version_id);
"""


class SQLiteCanonicalRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(_SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _scope(scope: OwnershipScope) -> tuple[str, str]:
        return scope.tenant_id, scope.project_id

    def create_version(
        self, document: CanonicalDocument, version: DocumentVersion
    ) -> tuple[DocumentVersion, bool]:
        if document.document_id != version.document_id or document.scope != version.scope:
            raise ValueError("document/version identity or ownership mismatch")
        with self.transaction() as db:
            existing = db.execute(
                "SELECT tenant_id,project_id FROM documents WHERE document_id=?",
                (document.document_id,),
            ).fetchone()
            if existing is not None and tuple(existing) != self._scope(document.scope):
                raise PermissionError("document is outside ownership scope")
            db.execute(
                "INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    document.document_id,
                    *self._scope(document.scope),
                    document.logical_source,
                    document.media_type,
                    document.status,
                    document.active_version_id,
                    document.created_at.isoformat(),
                    None,
                ),
            )
            row = db.execute(
                "SELECT version_id FROM document_versions WHERE document_id=? AND source_hash=?",
                (version.document_id, version.source_hash),
            ).fetchone()
            if row is not None:
                return self.get_version(version.scope, str(row[0])), False
            if db.execute(
                "SELECT 1 FROM document_versions WHERE version_id=?", (version.version_id,)
            ).fetchone():
                raise ImmutableVersionError(
                    "version identity already has different immutable content"
                )
            db.execute(
                "INSERT INTO document_versions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    version.version_id,
                    version.document_id,
                    *self._scope(version.scope),
                    version.source_hash,
                    version.source_locator.model_dump_json(),
                    version.media_type,
                    version.parser_fingerprint,
                    version.status,
                    version.created_at.isoformat(),
                ),
            )
        return version, True

    def get_version(self, scope: OwnershipScope, version_id: str) -> DocumentVersion:
        row = self.connection.execute(
            "SELECT * FROM document_versions WHERE version_id=? AND tenant_id=? AND project_id=?",
            (version_id, *self._scope(scope)),
        ).fetchone()
        if row is None:
            raise KeyError(version_id)
        return DocumentVersion.model_validate(
            {
                "version_id": row["version_id"],
                "document_id": row["document_id"],
                "scope": scope.model_dump(),
                "source_hash": row["source_hash"],
                "source_locator": SourceLocator.model_validate_json(row["source_locator_json"]),
                "media_type": row["media_type"],
                "parser_fingerprint": row["parser_fingerprint"],
                "status": DocumentStatus(row["status"]),
                "created_at": datetime.fromisoformat(row["created_at"]),
            }
        )

    def list_versions(self, scope: OwnershipScope, document_id: str) -> list[DocumentVersion]:
        rows = self.connection.execute(
            "SELECT version_id FROM document_versions WHERE document_id=? AND tenant_id=? AND project_id=? ORDER BY created_at,version_id",
            (document_id, *self._scope(scope)),
        ).fetchall()
        return [self.get_version(scope, str(row[0])) for row in rows]

    def put_blocks(self, scope: OwnershipScope, blocks: Iterable[NormalizedBlock]) -> int:
        count = 0
        with self.transaction() as db:
            for block in blocks:
                self.get_version(scope, block.version_id)
                db.execute(
                    "INSERT OR REPLACE INTO document_blocks VALUES(?,?,?,?,?,?)",
                    (
                        block.block_id,
                        block.version_id,
                        *self._scope(scope),
                        block.ordinal,
                        block.model_dump_json(),
                    ),
                )
                count += 1
        return count

    def put_chunks(self, scope: OwnershipScope, chunks: Iterable[DocumentChunk]) -> int:
        count = 0
        with self.transaction() as db:
            for chunk in chunks:
                if chunk.scope != scope:
                    raise PermissionError("chunk is outside ownership scope")
                self.get_version(scope, chunk.version_id)
                db.execute(
                    "INSERT OR REPLACE INTO document_chunks VALUES(?,?,?,?,?,?,?)",
                    (
                        chunk.chunk_id,
                        chunk.version_id,
                        *self._scope(scope),
                        chunk.ordinal,
                        chunk.content_hash,
                        chunk.model_dump_json(),
                    ),
                )
                count += 1
        return count

    def get_chunks(
        self, scope: OwnershipScope, chunk_ids: Sequence[str], *, active_only: bool = True
    ) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        marks = ",".join("?" for _ in chunk_ids)
        active = (
            "AND d.status='ready' AND v.status='ready' AND d.active_version_id=v.version_id"
            if active_only
            else ""
        )
        rows = self.connection.execute(
            f"SELECT c.payload_json FROM document_chunks c JOIN document_versions v ON v.version_id=c.version_id JOIN documents d ON d.document_id=v.document_id WHERE c.chunk_id IN ({marks}) AND c.tenant_id=? AND c.project_id=? {active} ORDER BY c.ordinal,c.chunk_id",
            (*chunk_ids, *self._scope(scope)),
        ).fetchall()
        return [DocumentChunk.model_validate_json(row[0]) for row in rows]

    def activate_version(self, scope: OwnershipScope, document_id: str, version_id: str) -> None:
        version = self.get_version(scope, version_id)
        if version.document_id != document_id:
            raise KeyError(version_id)
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE documents SET active_version_id=?,status='ready' WHERE document_id=? AND tenant_id=? AND project_id=?",
                (version_id, document_id, *self._scope(scope)),
            ).rowcount
            if not changed:
                raise KeyError(document_id)
            db.execute(
                "UPDATE document_versions SET status=CASE WHEN version_id=? THEN 'ready' ELSE 'superseded' END WHERE document_id=? AND tenant_id=? AND project_id=?",
                (version_id, document_id, *self._scope(scope)),
            )

    def tombstone(self, scope: OwnershipScope, document_id: str) -> int:
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE documents SET status='tombstoned',active_version_id=NULL,tombstoned_at=? WHERE document_id=? AND tenant_id=? AND project_id=?",
                (datetime.now(UTC).isoformat(), document_id, *self._scope(scope)),
            ).rowcount
            if changed:
                db.execute(
                    "UPDATE document_versions SET status='tombstoned' WHERE document_id=? AND tenant_id=? AND project_id=?",
                    (document_id, *self._scope(scope)),
                )
            return changed

    def save_job(self, job: IngestionJob) -> None:
        self.connection.execute(
            "INSERT INTO ingestion_jobs VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET stage=excluded.stage,payload_json=excluded.payload_json,updated_at=excluded.updated_at",
            (
                job.job_id,
                *self._scope(job.scope),
                job.document_id,
                job.idempotency_key,
                job.stage,
                job.model_dump_json(),
                job.updated_at.isoformat(),
            ),
        )
        self.connection.commit()

    def get_job(self, scope: OwnershipScope, job_id: str) -> IngestionJob:
        row = self.connection.execute(
            "SELECT payload_json FROM ingestion_jobs WHERE job_id=? AND tenant_id=? AND project_id=?",
            (job_id, *self._scope(scope)),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return IngestionJob.model_validate_json(row[0])

    def save_manifest(self, manifest: IndexManifest) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO index_manifests VALUES(?,?,?,?,?,?)",
            (
                manifest.manifest_id,
                manifest.collection_name,
                manifest.alias,
                manifest.generation,
                manifest.status,
                manifest.model_dump_json(),
            ),
        )
        self.connection.commit()

    def list_manifests(self) -> list[IndexManifest]:
        rows = self.connection.execute(
            "SELECT payload_json FROM index_manifests ORDER BY generation"
        ).fetchall()
        return [IndexManifest.model_validate_json(row[0]) for row in rows]

    def resolve_chunks_to_legacy(
        self, scope: OwnershipScope, chunk_ids: Sequence[str]
    ) -> dict[str, tuple[str, str, str]]:
        """Resolve only mappings whose document/version is currently active and ready."""
        if not chunk_ids:
            return {}
        marks = ",".join("?" for _ in chunk_ids)
        rows = self.connection.execute(
            f"SELECT m.chunk_id,m.evidence_id,m.document_id,m.version_id "
            f"FROM legacy_evidence_mappings m "
            f"JOIN documents d ON d.document_id=m.document_id "
            f"JOIN document_versions v ON v.version_id=m.version_id "
            f"WHERE m.chunk_id IN ({marks}) AND m.tenant_id=? AND m.project_id=? "
            f"AND d.tenant_id=m.tenant_id AND d.project_id=m.project_id "
            f"AND v.tenant_id=m.tenant_id AND v.project_id=m.project_id "
            f"AND d.status='ready' AND v.status='ready' "
            f"AND d.active_version_id=m.version_id",
            (*chunk_ids, *self._scope(scope)),
        ).fetchall()
        return {str(row[0]): (str(row[1]), str(row[2]), str(row[3])) for row in rows}

    def map_legacy(
        self,
        evidence_id: str,
        scope: OwnershipScope,
        document_id: str,
        version_id: str,
        chunk_id: str,
        source_row: int,
    ) -> None:
        self.get_version(scope, version_id)
        self.connection.execute(
            "INSERT OR REPLACE INTO legacy_evidence_mappings VALUES(?,?,?,?,?,?,?)",
            (evidence_id, *self._scope(scope), document_id, version_id, chunk_id, source_row),
        )
        self.connection.commit()

    def resolve_legacy(self, scope: OwnershipScope, evidence_id: str) -> tuple[str, str, str]:
        row = self.connection.execute(
            "SELECT document_id,version_id,chunk_id FROM legacy_evidence_mappings WHERE evidence_id=? AND tenant_id=? AND project_id=?",
            (evidence_id, *self._scope(scope)),
        ).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return str(row[0]), str(row[1]), str(row[2])

    def cache_embedding(self, content_hash: str, fingerprint: str, vector: Sequence[float]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO embedding_cache VALUES(?,?,?,?,?)",
            (
                content_hash,
                fingerprint,
                len(vector),
                json.dumps(vector),
                datetime.now(UTC).isoformat(),
            ),
        )
        self.connection.commit()

    def get_cached_embedding(self, content_hash: str, fingerprint: str) -> list[float] | None:
        row = self.connection.execute(
            "SELECT vector_json FROM embedding_cache WHERE content_hash=? AND embedding_fingerprint=?",
            (content_hash, fingerprint),
        ).fetchone()
        return None if row is None else [float(value) for value in json.loads(row[0])]

    def close(self) -> None:
        self.connection.close()
