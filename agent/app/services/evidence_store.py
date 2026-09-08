from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from threading import RLock
from typing import Final

from app.models.evidence import (
    DataQualityReport,
    LiteratureRecord,
    LiteratureSearchHit,
    LiteratureSearchInput,
    LiteratureSearchOutput,
)
from app.services.evidence_importer import SCHEMA_VERSION, import_literature, source_sha256


class EvidenceIndexError(RuntimeError):
    """Raised when the durable evidence index cannot be initialized."""


_FIELDS: Final = (
    "title",
    "link_or_doi",
    "year",
    "country",
    "authors",
    "first_affiliation",
    "herbs",
    "compounds",
    "metal_ions",
    "organic_macromolecules",
    "decoction_composition",
    "assembly_composition",
    "assembly_morphology",
    "assembly_phase",
    "solvent_type",
    "ph",
    "temperature",
    "interaction_types",
    "interaction_sites",
    "average_size",
    "pdi",
    "zeta_potential",
    "cac_cmc",
    "tgel",
    "clinical_problem",
    "pharmacodynamic_indicators",
    "efficacy_comparison",
    "mechanism",
    "remarks",
)


_HERB_ALIASES: Final = {
    "甘草": ("甘草", "gancao", "licorice", "glycyrrhiza"),
    "当归": ("当归", "danggui", "angelica"),
    "黄芪": ("黄芪", "huangqi", "astragalus"),
}


def _normalize(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).lower().split())


def _fts_query(value: str) -> str | None:
    tokens = [token for token in value.replace('"', " ").split() if token]
    return " OR ".join(f'"{token}"' for token in tokens) or None


class EvidenceStore:
    def __init__(self, source_path: str | Path, database_path: str | Path) -> None:
        self.source_path = Path(source_path)
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self.ensure_index()

    def _connect(self, path: Path | None = None) -> sqlite3.Connection:
        connection = sqlite3.connect(
            path or self.database_path, timeout=5.0, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS temp.fts5_probe USING fts5(value)"
            )
            connection.execute("DROP TABLE temp.fts5_probe")
        except sqlite3.OperationalError as exc:
            connection.close()
            raise EvidenceIndexError(
                "SQLite FTS5 is required for literature indexing but is unavailable"
            ) from exc
        return connection

    def _current_hash(self) -> str | None:
        if not self.database_path.exists():
            return None
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT value FROM evidence_metadata WHERE key = 'source_hash'"
            ).fetchone()
            schema = connection.execute(
                "SELECT value FROM evidence_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None or schema is None or schema[0] != SCHEMA_VERSION:
                return None
            return str(row[0])
        except sqlite3.OperationalError:
            return None
        finally:
            connection.close()

    def ensure_index(self) -> bool:
        if not self.source_path.is_file():
            raise EvidenceIndexError(f"Evidence source file not found: {self.source_path}")
        digest = source_sha256(self.source_path)
        with self._lock:
            if self._current_hash() == digest:
                self._ensure_open()
                return False
            records, report = import_literature(self.source_path)
            self._atomic_rebuild(records, report)
            self._ensure_open()
            return True

    def _atomic_rebuild(self, records: list[LiteratureRecord], report: DataQualityReport) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.database_path.name}.", suffix=".tmp", dir=self.database_path.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect(temporary)
            connection.executescript(
                """
                CREATE TABLE evidence_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE literature_records (
                    document_id TEXT PRIMARY KEY, title TEXT, link_or_doi TEXT, year INTEGER,
                    country TEXT, authors TEXT, first_affiliation TEXT, herbs TEXT, compounds TEXT,
                    smiles_json TEXT NOT NULL, metal_ions TEXT, organic_macromolecules TEXT,
                    decoction_composition TEXT, assembly_composition TEXT,
                    assembly_morphology TEXT, assembly_phase TEXT, solvent_type TEXT, ph TEXT,
                    temperature TEXT, interaction_types TEXT, interaction_sites TEXT,
                    average_size TEXT, pdi TEXT, zeta_potential TEXT, cac_cmc TEXT, tgel TEXT,
                    clinical_problem TEXT, pharmacodynamic_indicators TEXT,
                    efficacy_comparison TEXT, mechanism TEXT, remarks TEXT,
                    normalized_herbs TEXT NOT NULL, normalized_compounds TEXT NOT NULL,
                    source_file TEXT NOT NULL, sheet TEXT NOT NULL, source_row INTEGER NOT NULL,
                    source_hash TEXT NOT NULL, schema_version TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE literature_fts USING fts5(
                    document_id UNINDEXED, title, authors, herbs, compounds,
                    assembly_morphology, interaction_types, mechanism, remarks,
                    tokenize='unicode61'
                );
                """
            )
            digest = report.source_sha256
            insert_fields = ", ".join(_FIELDS)
            placeholders = ", ".join("?" for _ in range(len(_FIELDS) + 9))
            for record in records:
                values = [getattr(record, field) for field in _FIELDS]
                connection.execute(
                    f"INSERT INTO literature_records (document_id, {insert_fields}, smiles_json, "
                    "normalized_herbs, normalized_compounds, source_file, sheet, source_row, "
                    f"source_hash, schema_version) VALUES ({placeholders})",
                    [
                        record.document_id,
                        *values,
                        json.dumps(record.small_molecule_smiles),
                        _normalize(record.herbs or ""),
                        _normalize(record.compounds or ""),
                        record.source_file,
                        record.sheet,
                        record.source_row,
                        digest,
                        SCHEMA_VERSION,
                    ],
                )
                connection.execute(
                    "INSERT INTO literature_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.document_id,
                        record.title,
                        record.authors,
                        record.herbs,
                        record.compounds,
                        record.assembly_morphology,
                        record.interaction_types,
                        record.mechanism,
                        record.remarks,
                    ),
                )
            connection.executemany(
                "INSERT INTO evidence_metadata VALUES (?, ?)",
                (
                    ("source_hash", digest),
                    ("schema_version", SCHEMA_VERSION),
                    ("quality_report", report.model_dump_json()),
                ),
            )
            connection.commit()
            connection.close()
            connection = None
            self.close()
            os.replace(temporary, self.database_path)
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise EvidenceIndexError(f"Failed to build evidence index: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
            temporary.unlink(missing_ok=True)

    def _ensure_open(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = self._connect()
            self._connection.execute("PRAGMA journal_mode=WAL")
        return self._connection

    def quality_report(self) -> DataQualityReport:
        with self._lock:
            row = (
                self._ensure_open()
                .execute("SELECT value FROM evidence_metadata WHERE key = 'quality_report'")
                .fetchone()
            )
            if row is None:
                raise EvidenceIndexError("Evidence quality metadata is missing")
            return DataQualityReport.model_validate_json(row[0])

    def search(self, request: LiteratureSearchInput) -> LiteratureSearchOutput:
        with self._lock:
            connection = self._ensure_open()
            channels: dict[str, dict[str, float]] = {
                "fts_bm25": {},
                "herb": {},
                "compound": {},
                "smiles": {},
            }
            matched: dict[str, set[str]] = {}
            query = _fts_query(request.query or "")
            if query is not None:
                rows = connection.execute(
                    "SELECT document_id, bm25(literature_fts) AS rank FROM literature_fts "
                    "WHERE literature_fts MATCH ? ORDER BY rank, document_id LIMIT 500",
                    (query,),
                ).fetchall()
                for rank, row in enumerate(rows, start=1):
                    identifier = str(row["document_id"])
                    channels["fts_bm25"][identifier] = 1.0 / rank
                    matched.setdefault(identifier, set()).add("full_text")
            self._contains_channel(
                connection, request.herbs, "normalized_herbs", "herb", channels, matched
            )
            self._contains_channel(
                connection, request.compounds, "normalized_compounds", "compound", channels, matched
            )
            if request.smiles:
                wanted = set(request.smiles)
                for row in connection.execute(
                    "SELECT document_id, smiles_json FROM literature_records"
                ):
                    if wanted.intersection(json.loads(row["smiles_json"])):
                        identifier = str(row["document_id"])
                        channels["smiles"][identifier] = 1.0
                        matched.setdefault(identifier, set()).add("smiles")
            identifiers = set().union(*(channel.keys() for channel in channels.values()))
            hits: list[LiteratureSearchHit] = []
            for identifier in identifiers:
                row = connection.execute(
                    "SELECT * FROM literature_records WHERE document_id = ?", (identifier,)
                ).fetchone()
                if row is None:
                    continue
                scores = {name: values.get(identifier, 0.0) for name, values in channels.items()}
                final = (
                    0.45 * scores["fts_bm25"]
                    + 0.2 * scores["herb"]
                    + 0.2 * scores["compound"]
                    + 0.15 * scores["smiles"]
                )
                snippet = next(
                    (row[field] for field in ("mechanism", "remarks", "title") if row[field]), None
                )
                hits.append(
                    LiteratureSearchHit(
                        document_id=identifier,
                        title=row["title"],
                        link_or_doi=row["link_or_doi"],
                        year=row["year"],
                        source_row=row["source_row"],
                        herbs=row["herbs"],
                        compounds=row["compounds"],
                        smiles=json.loads(row["smiles_json"]),
                        conditions={
                            "assembly_morphology": row["assembly_morphology"],
                            "assembly_phase": row["assembly_phase"],
                            "solvent_type": row["solvent_type"],
                            "ph": row["ph"],
                            "temperature": row["temperature"],
                            "interaction_types": row["interaction_types"],
                        },
                        final_score=round(final, 8),
                        channel_scores={k: round(v, 8) for k, v in scores.items()},
                        matched_fields=sorted(matched.get(identifier, set())),
                        snippet=snippet,
                    )
                )
            hits.sort(
                key=lambda hit: (
                    -hit.final_score,
                    -(hit.year or -1),
                    hit.source_row,
                    hit.document_id,
                )
            )
            digest = self.quality_report().source_sha256
            return LiteratureSearchOutput(
                query=request,
                hits=hits[: request.top_k],
                total_candidates=len(hits),
                source_sha256=digest,
                degraded=not hits,
            )

    @staticmethod
    def _contains_channel(
        connection: sqlite3.Connection,
        terms: list[str],
        column: str,
        channel: str,
        channels: dict[str, dict[str, float]],
        matched: dict[str, set[str]],
    ) -> None:
        normalized = [
            tuple(_normalize(alias) for alias in _HERB_ALIASES.get(term, (term,)))
            if channel == "herb"
            else (_normalize(term),)
            for term in terms
            if _normalize(term)
        ]
        if not normalized:
            return
        for row in connection.execute(f"SELECT document_id, {column} FROM literature_records"):
            matches = sum(any(alias in row[column] for alias in aliases) for aliases in normalized)
            if matches:
                identifier = str(row["document_id"])
                channels[channel][identifier] = matches / len(normalized)
                matched.setdefault(identifier, set()).add(
                    "herbs" if channel == "herb" else "compounds"
                )

    def get_hits(self, document_ids: list[str]) -> list[LiteratureSearchHit]:
        """Resolve exact legacy evidence IDs without broadening retrieval scope."""
        if not document_ids:
            return []
        with self._lock:
            connection = self._ensure_open()
            marks = ",".join("?" for _ in document_ids)
            rows = connection.execute(
                f"SELECT * FROM literature_records WHERE document_id IN ({marks})",
                tuple(document_ids),
            ).fetchall()
            return [
                LiteratureSearchHit(
                    document_id=str(row["document_id"]),
                    title=row["title"],
                    link_or_doi=row["link_or_doi"],
                    year=row["year"],
                    source_row=row["source_row"],
                    herbs=row["herbs"],
                    compounds=row["compounds"],
                    smiles=json.loads(row["smiles_json"]),
                    conditions={
                        "assembly_morphology": row["assembly_morphology"],
                        "assembly_phase": row["assembly_phase"],
                        "solvent_type": row["solvent_type"],
                        "ph": row["ph"],
                        "temperature": row["temperature"],
                        "interaction_types": row["interaction_types"],
                    },
                    final_score=0.0,
                    channel_scores={},
                    matched_fields=[],
                    snippet=next(
                        (row[field] for field in ("mechanism", "remarks", "title") if row[field]),
                        None,
                    ),
                )
                for row in rows
            ]

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
