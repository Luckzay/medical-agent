-- Agent durable state and canonical knowledge storage (MySQL 8 / InnoDB).
CREATE TABLE IF NOT EXISTS `agent_workflow_runs` (
  `run_id` VARCHAR(128) NOT NULL,
  `user_id` BIGINT NOT NULL,
  `trace_id` VARCHAR(128) NOT NULL,
  `herbs_json` JSON NOT NULL,
  `research_goal` TEXT NULL,
  `status` VARCHAR(32) NOT NULL,
  `analysis_result_json` JSON NULL,
  `workflow_json` JSON NULL,
  `error_message` TEXT NULL,
  `created_at` DATETIME(6) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`run_id`), KEY `idx_agent_workflow_runs_status` (`status`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `agent_chat_turns` (
  `turn_id` VARCHAR(128) NOT NULL,
  `session_id` VARCHAR(128) NOT NULL,
  `user_id` VARCHAR(128) NOT NULL,
  `message` TEXT NOT NULL,
  `history_json` JSON NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `assistant_message` LONGTEXT NULL,
  `error_message` TEXT NULL,
  `next_event_sequence` BIGINT UNSIGNED NOT NULL DEFAULT 1,
  `created_at` DATETIME(6) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`turn_id`), KEY `idx_agent_chat_turns_status` (`status`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `agent_chat_events` (
  `turn_id` VARCHAR(128) NOT NULL,
  `sequence` BIGINT UNSIGNED NOT NULL,
  `type` VARCHAR(64) NOT NULL,
  `node` VARCHAR(128) NOT NULL,
  `status` VARCHAR(64) NOT NULL,
  `detail` TEXT NOT NULL,
  `delta` LONGTEXT NULL,
  `tool_name` VARCHAR(128) NULL,
  `tool_call_id` VARCHAR(128) NULL,
  `input_json` JSON NULL,
  `output_json` JSON NULL,
  `created_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`turn_id`,`sequence`),
  CONSTRAINT `fk_agent_chat_events_turn` FOREIGN KEY (`turn_id`)
    REFERENCES `agent_chat_turns` (`turn_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `agent_tool_audits` (
  `audit_id` CHAR(32) NOT NULL,
  `run_id` VARCHAR(128) NOT NULL,
  `node` VARCHAR(128) NOT NULL,
  `tool_name` VARCHAR(128) NOT NULL,
  `tool_version` VARCHAR(64) NOT NULL,
  `started_at` DATETIME(6) NOT NULL,
  `completed_at` DATETIME(6) NOT NULL,
  `duration_ms` BIGINT UNSIGNED NOT NULL,
  `status` VARCHAR(64) NOT NULL,
  `attempts` INT UNSIGNED NOT NULL,
  `error_type` VARCHAR(255) NULL,
  `error_message` VARCHAR(300) NULL,
  PRIMARY KEY (`audit_id`), KEY `idx_agent_tool_audits_run` (`run_id`,`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_documents` (
  `document_id` CHAR(36) NOT NULL, `tenant_id` VARCHAR(128) NOT NULL,
  `project_id` VARCHAR(128) NOT NULL, `logical_source` VARCHAR(384) NOT NULL,
  `media_type` VARCHAR(128) NOT NULL, `status` VARCHAR(32) NOT NULL,
  `active_version_id` CHAR(36) NULL, `created_at` DATETIME(6) NOT NULL,
  `tombstoned_at` DATETIME(6) NULL, PRIMARY KEY (`document_id`),
  UNIQUE KEY `uk_knowledge_document_source` (`tenant_id`,`project_id`,`logical_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_document_versions` (
  `version_id` CHAR(36) NOT NULL, `document_id` CHAR(36) NOT NULL,
  `tenant_id` VARCHAR(128) NOT NULL, `project_id` VARCHAR(128) NOT NULL,
  `source_hash` CHAR(64) NOT NULL, `source_locator_json` JSON NOT NULL,
  `media_type` VARCHAR(128) NOT NULL, `parser_fingerprint` VARCHAR(512) NOT NULL,
  `status` VARCHAR(32) NOT NULL, `created_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`version_id`), UNIQUE KEY `uk_knowledge_version_hash` (`document_id`,`source_hash`),
  KEY `idx_knowledge_versions_scope` (`tenant_id`,`project_id`,`document_id`),
  CONSTRAINT `fk_knowledge_versions_document` FOREIGN KEY (`document_id`)
    REFERENCES `knowledge_documents` (`document_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_document_blocks` (
  `block_id` CHAR(36) NOT NULL, `version_id` CHAR(36) NOT NULL,
  `tenant_id` VARCHAR(128) NOT NULL, `project_id` VARCHAR(128) NOT NULL,
  `ordinal` INT UNSIGNED NOT NULL, `payload_json` JSON NOT NULL,
  PRIMARY KEY (`block_id`), UNIQUE KEY `uk_knowledge_block_ordinal` (`version_id`,`ordinal`),
  CONSTRAINT `fk_knowledge_blocks_version` FOREIGN KEY (`version_id`)
    REFERENCES `knowledge_document_versions` (`version_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_document_chunks` (
  `chunk_id` CHAR(36) NOT NULL, `version_id` CHAR(36) NOT NULL,
  `tenant_id` VARCHAR(128) NOT NULL, `project_id` VARCHAR(128) NOT NULL,
  `ordinal` INT UNSIGNED NOT NULL, `content_hash` CHAR(64) NOT NULL,
  `payload_json` JSON NOT NULL, PRIMARY KEY (`chunk_id`),
  UNIQUE KEY `uk_knowledge_chunk_ordinal` (`version_id`,`ordinal`),
  KEY `idx_knowledge_chunks_scope` (`tenant_id`,`project_id`,`version_id`),
  CONSTRAINT `fk_knowledge_chunks_version` FOREIGN KEY (`version_id`)
    REFERENCES `knowledge_document_versions` (`version_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_ingestion_jobs` (
  `job_id` CHAR(36) NOT NULL, `tenant_id` VARCHAR(128) NOT NULL,
  `project_id` VARCHAR(128) NOT NULL, `document_id` CHAR(36) NOT NULL,
  `idempotency_key` VARCHAR(512) NOT NULL, `stage` VARCHAR(32) NOT NULL,
  `payload_json` JSON NOT NULL, `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`job_id`), UNIQUE KEY `uk_knowledge_job_idempotency` (`tenant_id`,`project_id`,`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_embedding_cache` (
  `content_hash` CHAR(64) NOT NULL, `embedding_fingerprint` VARCHAR(512) NOT NULL,
  `dimension` INT UNSIGNED NOT NULL, `vector_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`content_hash`,`embedding_fingerprint`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_index_manifests` (
  `manifest_id` CHAR(36) NOT NULL, `collection_name` VARCHAR(255) NOT NULL,
  `alias` VARCHAR(255) NOT NULL, `generation` VARCHAR(128) NOT NULL,
  `status` VARCHAR(32) NOT NULL, `payload_json` JSON NOT NULL,
  PRIMARY KEY (`manifest_id`), UNIQUE KEY `uk_knowledge_manifest_collection` (`collection_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_legacy_evidence_mappings` (
  `evidence_id` VARCHAR(255) NOT NULL, `tenant_id` VARCHAR(128) NOT NULL,
  `project_id` VARCHAR(128) NOT NULL, `document_id` CHAR(36) NOT NULL,
  `version_id` CHAR(36) NOT NULL, `chunk_id` CHAR(36) NOT NULL,
  `source_row` INT NOT NULL, PRIMARY KEY (`evidence_id`), KEY `idx_knowledge_legacy_chunk` (`chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_toxicology_snapshots` (
  `snapshot_id` CHAR(36) NOT NULL, `source_snapshot` CHAR(64) NOT NULL,
  `created_at` DATETIME(6) NOT NULL, PRIMARY KEY (`snapshot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_toxicology_herbs` (
  `herb_id` BIGINT NOT NULL, `name` VARCHAR(255) NOT NULL, `common_name` VARCHAR(255) NULL,
  `logical_source` VARCHAR(768) NOT NULL, `reference` VARCHAR(255) NOT NULL,
  `virulence` TEXT NULL, `toxicity_mechanism` TEXT NULL, `pathological_examination` TEXT NULL,
  `crowd_taboo` TEXT NULL, `symptom_contraindications` TEXT NULL, `adr` TEXT NULL,
  `typical_cases_of_adr` TEXT NULL, `clinical_suggestion` TEXT NULL,
  `clinical_suggestion_basis` TEXT NULL, `link_to_clinical_suggestion` VARCHAR(1024) NULL,
  `created_at` DATETIME(6) NOT NULL, PRIMARY KEY (`herb_id`), UNIQUE KEY `uk_knowledge_toxicology_reference` (`reference`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `knowledge_toxicology_compounds` (
  `compound_id` BIGINT NOT NULL, `herb_id` BIGINT NOT NULL, `name` VARCHAR(512) NULL,
  `formula` VARCHAR(255) NULL, `cas` VARCHAR(255) NULL, `logical_source` VARCHAR(768) NOT NULL,
  `created_at` DATETIME(6) NOT NULL, PRIMARY KEY (`compound_id`), KEY `idx_knowledge_toxicology_compound_herb` (`herb_id`),
  CONSTRAINT `fk_knowledge_toxicology_compound_herb` FOREIGN KEY (`herb_id`)
    REFERENCES `knowledge_toxicology_herbs` (`herb_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
