from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

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
from app.services.infrastructure.mysql import MySQLDatabase


class ImmutableVersionError(ValueError):
    pass


def _json_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


class MySQLCanonicalRepository:
    """Canonical knowledge metadata repository backed exclusively by MySQL/InnoDB."""

    def __init__(self, database: MySQLDatabase | None = None) -> None:
        self.database = database or MySQLDatabase()

    @staticmethod
    def _scope(scope: OwnershipScope) -> tuple[str, str]:
        return scope.tenant_id, scope.project_id

    def create_version(
        self, document: CanonicalDocument, version: DocumentVersion
    ) -> tuple[DocumentVersion, bool]:
        if document.document_id != version.document_id or document.scope != version.scope:
            raise ValueError("document/version identity or ownership mismatch")
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tenant_id,project_id FROM knowledge_documents "
                    "WHERE document_id=%s FOR UPDATE",
                    (document.document_id,),
                )
                existing = cursor.fetchone()
                if existing is not None and (
                    existing["tenant_id"], existing["project_id"]
                ) != self._scope(document.scope):
                    raise PermissionError("document is outside ownership scope")
                cursor.execute(
                    """INSERT IGNORE INTO knowledge_documents
                    (document_id,tenant_id,project_id,logical_source,media_type,status,
                     active_version_id,created_at,tombstoned_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NULL)""",
                    (
                        document.document_id,
                        *self._scope(document.scope),
                        document.logical_source,
                        document.media_type,
                        document.status,
                        document.active_version_id,
                        document.created_at.replace(tzinfo=None),
                    ),
                )
                cursor.execute(
                    """SELECT version_id FROM knowledge_document_versions
                    WHERE document_id=%s AND source_hash=%s""",
                    (version.document_id, version.source_hash),
                )
                row = cursor.fetchone()
                if row is not None:
                    return self.get_version(version.scope, str(row["version_id"])), False
                cursor.execute(
                    "SELECT 1 FROM knowledge_document_versions WHERE version_id=%s",
                    (version.version_id,),
                )
                if cursor.fetchone():
                    raise ImmutableVersionError(
                        "version identity already has different immutable content"
                    )
                cursor.execute(
                    """INSERT INTO knowledge_document_versions
                    (version_id,document_id,tenant_id,project_id,source_hash,
                     source_locator_json,media_type,parser_fingerprint,status,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        version.version_id,
                        version.document_id,
                        *self._scope(version.scope),
                        version.source_hash,
                        version.source_locator.model_dump_json(),
                        version.media_type,
                        version.parser_fingerprint,
                        version.status,
                        version.created_at.replace(tzinfo=None),
                    ),
                )
        return version, True

    def get_version(self, scope: OwnershipScope, version_id: str) -> DocumentVersion:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM knowledge_document_versions
                WHERE version_id=%s AND tenant_id=%s AND project_id=%s""",
                (version_id, *self._scope(scope)),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(version_id)
        return DocumentVersion.model_validate(
            {
                "version_id": row["version_id"],
                "document_id": row["document_id"],
                "scope": scope.model_dump(),
                "source_hash": row["source_hash"],
                "source_locator": SourceLocator.model_validate_json(
                    _json_text(row["source_locator_json"])
                ),
                "media_type": row["media_type"],
                "parser_fingerprint": row["parser_fingerprint"],
                "status": DocumentStatus(row["status"]),
                "created_at": row["created_at"],
            }
        )

    def list_versions(self, scope: OwnershipScope, document_id: str) -> list[DocumentVersion]:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT version_id FROM knowledge_document_versions
                WHERE document_id=%s AND tenant_id=%s AND project_id=%s
                ORDER BY created_at,version_id""",
                (document_id, *self._scope(scope)),
            )
            rows = cursor.fetchall()
        return [self.get_version(scope, str(row["version_id"])) for row in rows]

    def put_blocks(self, scope: OwnershipScope, blocks: Iterable[NormalizedBlock]) -> int:
        values = list(blocks)
        for block in values:
            self.get_version(scope, block.version_id)
        with self.database.cursor() as cursor:
            for block in values:
                cursor.execute(
                    """INSERT INTO knowledge_document_blocks
                    (block_id,version_id,tenant_id,project_id,ordinal,payload_json)
                    VALUES (%s,%s,%s,%s,%s,%s) AS new
                    ON DUPLICATE KEY UPDATE version_id=new.version_id,tenant_id=new.tenant_id,
                    project_id=new.project_id,ordinal=new.ordinal,payload_json=new.payload_json""",
                    (
                        block.block_id,
                        block.version_id,
                        *self._scope(scope),
                        block.ordinal,
                        block.model_dump_json(),
                    ),
                )
        return len(values)

    def put_chunks(self, scope: OwnershipScope, chunks: Iterable[DocumentChunk]) -> int:
        values = list(chunks)
        for chunk in values:
            if chunk.scope != scope:
                raise PermissionError("chunk is outside ownership scope")
            self.get_version(scope, chunk.version_id)
        with self.database.cursor() as cursor:
            for chunk in values:
                cursor.execute(
                    """INSERT INTO knowledge_document_chunks
                    (chunk_id,version_id,tenant_id,project_id,ordinal,content_hash,payload_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) AS new
                    ON DUPLICATE KEY UPDATE version_id=new.version_id,tenant_id=new.tenant_id,
                    project_id=new.project_id,ordinal=new.ordinal,content_hash=new.content_hash,
                    payload_json=new.payload_json""",
                    (
                        chunk.chunk_id,
                        chunk.version_id,
                        *self._scope(scope),
                        chunk.ordinal,
                        chunk.content_hash,
                        chunk.model_dump_json(),
                    ),
                )
        return len(values)

    def get_chunks(
        self, scope: OwnershipScope, chunk_ids: Sequence[str], *, active_only: bool = True
    ) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        marks = ",".join("%s" for _ in chunk_ids)
        active = (
            "AND d.status='ready' AND v.status='ready' AND d.active_version_id=v.version_id"
            if active_only
            else ""
        )
        with self.database.cursor() as cursor:
            cursor.execute(
                f"""SELECT c.payload_json FROM knowledge_document_chunks c
                JOIN knowledge_document_versions v ON v.version_id=c.version_id
                JOIN knowledge_documents d ON d.document_id=v.document_id
                WHERE c.chunk_id IN ({marks}) AND c.tenant_id=%s AND c.project_id=%s
                {active} ORDER BY c.ordinal,c.chunk_id""",
                (*chunk_ids, *self._scope(scope)),
            )
            rows = cursor.fetchall()
        return [DocumentChunk.model_validate_json(_json_text(row["payload_json"])) for row in rows]

    def active_chunks(self, scope: OwnershipScope) -> list[DocumentChunk]:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT c.payload_json FROM knowledge_document_chunks c
                JOIN knowledge_document_versions v ON v.version_id=c.version_id
                JOIN knowledge_documents d ON d.document_id=v.document_id
                WHERE c.tenant_id=%s AND c.project_id=%s AND d.status='ready'
                AND v.status='ready' AND d.active_version_id=v.version_id
                ORDER BY d.logical_source,c.ordinal""",
                self._scope(scope),
            )
            rows = cursor.fetchall()
        return [DocumentChunk.model_validate_json(_json_text(row["payload_json"])) for row in rows]

    def activate_version(self, scope: OwnershipScope, document_id: str, version_id: str) -> None:
        version = self.get_version(scope, version_id)
        if version.document_id != document_id:
            raise KeyError(version_id)
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE knowledge_documents SET active_version_id=%s,status='ready'
                    WHERE document_id=%s AND tenant_id=%s AND project_id=%s""",
                    (version_id, document_id, *self._scope(scope)),
                )
                if cursor.rowcount == 0:
                    raise KeyError(document_id)
                cursor.execute(
                    """UPDATE knowledge_document_versions
                    SET status=CASE WHEN version_id=%s THEN 'ready' ELSE 'superseded' END
                    WHERE document_id=%s AND tenant_id=%s AND project_id=%s""",
                    (version_id, document_id, *self._scope(scope)),
                )

    def tombstone(self, scope: OwnershipScope, document_id: str) -> int:
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE knowledge_documents SET status='tombstoned',active_version_id=NULL,
                    tombstoned_at=%s WHERE document_id=%s AND tenant_id=%s AND project_id=%s""",
                    (datetime.now(UTC).replace(tzinfo=None), document_id, *self._scope(scope)),
                )
                changed = int(cursor.rowcount)
                if changed:
                    cursor.execute(
                        """UPDATE knowledge_document_versions SET status='tombstoned'
                        WHERE document_id=%s AND tenant_id=%s AND project_id=%s""",
                        (document_id, *self._scope(scope)),
                    )
        return changed

    def find_job_by_idempotency(
        self, scope: OwnershipScope, idempotency_key: str
    ) -> IngestionJob | None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT payload_json FROM knowledge_ingestion_jobs
                WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s""",
                (*self._scope(scope), idempotency_key),
            )
            row = cursor.fetchone()
        return (
            IngestionJob.model_validate_json(_json_text(row["payload_json"])) if row else None
        )

    def save_job(self, job: IngestionJob) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_ingestion_jobs
                (job_id,tenant_id,project_id,document_id,idempotency_key,stage,payload_json,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) AS new
                ON DUPLICATE KEY UPDATE stage=new.stage,payload_json=new.payload_json,
                updated_at=new.updated_at""",
                (
                    job.job_id,
                    *self._scope(job.scope),
                    job.document_id,
                    job.idempotency_key,
                    job.stage,
                    job.model_dump_json(),
                    job.updated_at.replace(tzinfo=None),
                ),
            )

    def get_job(self, scope: OwnershipScope, job_id: str) -> IngestionJob:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT payload_json FROM knowledge_ingestion_jobs
                WHERE job_id=%s AND tenant_id=%s AND project_id=%s""",
                (job_id, *self._scope(scope)),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(job_id)
        return IngestionJob.model_validate_json(_json_text(row["payload_json"]))

    def save_manifest(self, manifest: IndexManifest) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_index_manifests
                (manifest_id,collection_name,alias,generation,status,payload_json)
                VALUES (%s,%s,%s,%s,%s,%s) AS new
                ON DUPLICATE KEY UPDATE collection_name=new.collection_name,alias=new.alias,
                generation=new.generation,status=new.status,payload_json=new.payload_json""",
                (
                    manifest.manifest_id,
                    manifest.collection_name,
                    manifest.alias,
                    manifest.generation,
                    manifest.status,
                    manifest.model_dump_json(),
                ),
            )

    def list_manifests(self) -> list[IndexManifest]:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT payload_json FROM knowledge_index_manifests ORDER BY generation")
            rows = cursor.fetchall()
        return [IndexManifest.model_validate_json(_json_text(row["payload_json"])) for row in rows]

    def resolve_toxicology_references(self, logical_sources: Sequence[str]) -> dict[str, str]:
        if not logical_sources:
            return {}
        values = list(dict.fromkeys(logical_sources))
        marks = ",".join("%s" for _ in values)
        with self.database.cursor() as cursor:
            cursor.execute(
                f"SELECT logical_source,reference FROM knowledge_toxicology_herbs "
                f"WHERE logical_source IN ({marks})",
                values,
            )
            rows = cursor.fetchall()
        return {str(row["logical_source"]): str(row["reference"]) for row in rows}

    def resolve_chunks_to_legacy(
        self, scope: OwnershipScope, chunk_ids: Sequence[str]
    ) -> dict[str, tuple[str, str, str]]:
        if not chunk_ids:
            return {}
        marks = ",".join("%s" for _ in chunk_ids)
        with self.database.cursor() as cursor:
            cursor.execute(
                f"""SELECT m.chunk_id,m.evidence_id,m.document_id,m.version_id
                FROM knowledge_legacy_evidence_mappings m
                JOIN knowledge_documents d ON d.document_id=m.document_id
                JOIN knowledge_document_versions v ON v.version_id=m.version_id
                WHERE m.chunk_id IN ({marks}) AND m.tenant_id=%s AND m.project_id=%s
                AND d.tenant_id=m.tenant_id AND d.project_id=m.project_id
                AND v.tenant_id=m.tenant_id AND v.project_id=m.project_id
                AND d.status='ready' AND v.status='ready' AND d.active_version_id=m.version_id""",
                (*chunk_ids, *self._scope(scope)),
            )
            rows = cursor.fetchall()
        return {
            str(row["chunk_id"]): (
                str(row["evidence_id"]),
                str(row["document_id"]),
                str(row["version_id"]),
            )
            for row in rows
        }

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
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_legacy_evidence_mappings
                (evidence_id,tenant_id,project_id,document_id,version_id,chunk_id,source_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s) AS new
                ON DUPLICATE KEY UPDATE tenant_id=new.tenant_id,project_id=new.project_id,
                document_id=new.document_id,version_id=new.version_id,chunk_id=new.chunk_id,
                source_row=new.source_row""",
                (evidence_id, *self._scope(scope), document_id, version_id, chunk_id, source_row),
            )

    def resolve_legacy(self, scope: OwnershipScope, evidence_id: str) -> tuple[str, str, str]:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT document_id,version_id,chunk_id
                FROM knowledge_legacy_evidence_mappings
                WHERE evidence_id=%s AND tenant_id=%s AND project_id=%s""",
                (evidence_id, *self._scope(scope)),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return str(row["document_id"]), str(row["version_id"]), str(row["chunk_id"])

    def cache_embedding(self, content_hash: str, fingerprint: str, vector: Sequence[float]) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_embedding_cache
                (content_hash,embedding_fingerprint,dimension,vector_json,created_at)
                VALUES (%s,%s,%s,%s,%s) AS new
                ON DUPLICATE KEY UPDATE dimension=new.dimension,vector_json=new.vector_json,
                created_at=new.created_at""",
                (
                    content_hash,
                    fingerprint,
                    len(vector),
                    json.dumps(vector),
                    datetime.now(UTC).replace(tzinfo=None),
                ),
            )

    def get_cached_embedding(self, content_hash: str, fingerprint: str) -> list[float] | None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT vector_json FROM knowledge_embedding_cache
                WHERE content_hash=%s AND embedding_fingerprint=%s""",
                (content_hash, fingerprint),
            )
            row = cursor.fetchone()
        return (
            None
            if row is None
            else [float(value) for value in json.loads(_json_text(row["vector_json"]))]
        )

    def list_active_documents(self, scope: OwnershipScope) -> list[Mapping[str, object]]:
        with self.database.cursor() as cursor:
            cursor.execute(
                """SELECT document_id,logical_source FROM knowledge_documents
                WHERE tenant_id=%s AND project_id=%s AND status!='tombstoned'""",
                self._scope(scope),
            )
            return list(cursor.fetchall())

    def toxicology_records(self, references: Sequence[str]) -> list[dict[str, object]]:
        if not references:
            return []
        marks = ",".join("%s" for _ in references)
        with self.database.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM knowledge_toxicology_herbs WHERE reference IN ({marks})",
                list(references),
            )
            herbs = list(cursor.fetchall())
            herb_ids = [row["herb_id"] for row in herbs]
            compounds: list[Mapping[str, object]] = []
            if herb_ids:
                compound_marks = ",".join("%s" for _ in herb_ids)
                cursor.execute(
                    f"""SELECT herb_id,name,formula,cas FROM knowledge_toxicology_compounds
                    WHERE herb_id IN ({compound_marks}) ORDER BY herb_id,compound_id""",
                    herb_ids,
                )
                compounds = list(cursor.fetchall())
        grouped: dict[object, list[Mapping[str, object]]] = {}
        for compound in compounds:
            grouped.setdefault(compound["herb_id"], []).append(compound)
        result = []
        for herb in herbs:
            item = dict(herb)
            item["toxic_compounds"] = grouped.get(herb["herb_id"], [])
            result.append(item)
        return result

    def replace_toxicology_snapshot(
        self, records: Sequence[Mapping[str, object]], database_name: str, snapshot: str
    ) -> None:
        created_at = datetime.now(UTC).replace(tzinfo=None)
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM knowledge_toxicology_compounds")
                cursor.execute("DELETE FROM knowledge_toxicology_herbs")
                cursor.execute("DELETE FROM knowledge_toxicology_snapshots")
                cursor.execute(
                    """INSERT INTO knowledge_toxicology_snapshots
                    (snapshot_id,source_snapshot,created_at) VALUES (UUID(),%s,%s)""",
                    (snapshot, created_at),
                )
                fields = (
                    "virulence,toxicity_mechanism,pathological_examination,crowd_taboo,"
                    "symptom_contraindications,adr,typical_cases_of_adr,clinical_suggestion,"
                    "clinical_suggestion_basis,link_to_clinical_suggestion"
                )
                field_names = fields.split(",")
                for herb in records:
                    herb_id = herb["id"]
                    cursor.execute(
                        f"""INSERT INTO knowledge_toxicology_herbs
                        (herb_id,name,common_name,logical_source,reference,{fields},created_at)
                        VALUES (%s,%s,%s,%s,%s,{','.join('%s' for _ in field_names)},%s)""",
                        (
                            herb_id,
                            herb["herb_name"],
                            herb.get("common_name"),
                            f"mysql://{database_name}/herb_basic/{herb_id}",
                            herb["reference"],
                            *(herb.get(field) for field in field_names),
                            created_at,
                        ),
                    )
                    compounds = cast(list[dict[str, Any]], herb.get("toxic_compounds", []))
                    for compound in compounds:
                        compound_id = compound["compound_id"]
                        cursor.execute(
                            """INSERT INTO knowledge_toxicology_compounds
                            (compound_id,herb_id,name,formula,cas,logical_source,created_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (
                                compound_id,
                                herb_id,
                                compound.get("compound_name"),
                                compound.get("formula"),
                                compound.get("cas"),
                                f"mysql://{database_name}/herb_toxiccompound/{compound_id}",
                                created_at,
                            ),
                        )

    def toxicology_counts(self) -> tuple[int, int]:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM knowledge_toxicology_herbs")
            herb_count = int(cursor.fetchone()["count"])
            cursor.execute(
                """SELECT COUNT(*) AS count FROM knowledge_toxicology_compounds c
                LEFT JOIN knowledge_toxicology_herbs h ON h.herb_id=c.herb_id
                WHERE h.herb_id IS NULL"""
            )
            orphan_count = int(cursor.fetchone()["count"])
        return herb_count, orphan_count

    def close(self) -> None:
        pass
