-- ============================================================================
-- AI Medical Database -- 鍏ㄦ柊搴撳垵濮嬪寲鑴氭湰
-- 绛栫暐: 涓嶄繚鐣欐棫 ID锛孉UTO_INCREMENT 鍏ㄩ儴閲嶆柊鐢熸垚
--       鍏宠仈琛ㄩ€氳繃瀹炰綋鍚嶇О JOIN 妗ユ帴鏃?ID -> 鏂?ID
--
-- 浣跨敤鏂瑰紡 (涓夋):
--   1) mysql -u root -p -e "CREATE DATABASE ai_medical_db_old;"
--   2) mysql -u root -p ai_medical_db_old < ai_medical_db_backup.sql
--   3) mysql -u root -p < init_new_database.sql
-- ============================================================================

DROP DATABASE IF EXISTS ai_medical_db;

CREATE DATABASE IF NOT EXISTS `ai_medical_db`
  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
USE `ai_medical_db`;


-- ============================================================================
-- 绗竴閮ㄥ垎: 寤鸿〃 (澶栭敭鍦ㄦ暟鎹縼绉诲畬鎴愬悗缁熶竴娣诲姞)
-- ============================================================================

-- 鐢ㄦ埛琛?

CREATE TABLE `users` (
  `id`           INT          NOT NULL AUTO_INCREMENT,
  `username`     VARCHAR(50)  NOT NULL,
  `password`     VARCHAR(255) NOT NULL COMMENT 'bcrypt hash',
  `full_name`    VARCHAR(50)  NOT NULL,
  `phone`        VARCHAR(20)  NOT NULL,
  `gender`       ENUM('male','female','other') NOT NULL DEFAULT 'other',
  `role`          
  `email`        VARCHAR(100) NOT NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`),
  UNIQUE KEY `uk_email`    (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鍒嗗瓙淇℃伅琛?

CREATE TABLE `molecular_info` (
  `record_number`                BIGINT       NOT NULL AUTO_INCREMENT,
  `record_title`                 VARCHAR(255) DEFAULT NULL,
  `record_description`           TEXT         DEFAULT NULL,
  `fda_pharmacology_summary`     TEXT         DEFAULT NULL,
  `livertox_summary`             TEXT         DEFAULT NULL,
  `inchi`                        VARCHAR(255) DEFAULT NULL,
  `inchi_key`                    VARCHAR(255) DEFAULT NULL,
  `smiles`                       VARCHAR(255) DEFAULT NULL,
  `molecular_formula`            VARCHAR(255) DEFAULT NULL,
  `molecular_weight`             DOUBLE       DEFAULT NULL,
  `xlogp3`                       DOUBLE       DEFAULT NULL,
  `hydrogen_bond_donor_count`    BIGINT       DEFAULT NULL,
  `hydrogen_bond_acceptor_count` BIGINT       DEFAULT NULL,
  `rotatable_bond_count`         BIGINT       DEFAULT NULL,
  `heavy_atom_count`             BIGINT       DEFAULT NULL,
  `created_at`                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`record_number`),
  UNIQUE KEY `uk_inchi_key` (`inchi_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 璁烘枃琛?

CREATE TABLE `papers` (
  `id`         INT          NOT NULL AUTO_INCREMENT,
  `title`      VARCHAR(1000) DEFAULT NULL,
  `authors`    VARCHAR(2000) DEFAULT NULL,
  `journal`    VARCHAR(200)  DEFAULT NULL,
  `year`       INT           DEFAULT NULL,
  `abstract`   TEXT          DEFAULT NULL,
  `doi`        VARCHAR(100)  DEFAULT NULL,
  `source_db`  VARCHAR(100)  DEFAULT NULL,
  `created_at` DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_doi` (`doi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 璁烘枃鏍囩鍏宠仈琛?

CREATE TABLE `paper_tags` (
  `paper_id` INT          NOT NULL,
  `tag`      VARCHAR(100) NOT NULL,
  PRIMARY KEY (`paper_id`, `tag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鏂瑰墏鍩虹琛?

CREATE TABLE `decoction_basic` (
  `id`                             INT          NOT NULL AUTO_INCREMENT,
  `decoction_name`                 VARCHAR(255) NOT NULL,
  `decoction_name_pinyin`          VARCHAR(255) DEFAULT NULL,
  `dosage_form`                    VARCHAR(255) DEFAULT NULL,
  `functionality`                  TEXT         DEFAULT NULL,
  `functionality_basis`            TEXT         DEFAULT NuULL,
  `link_to_functionality_basis`    VARCHAR(512) DEFAULT NULL,
  `usage_and_dosage`               TEXT         DEFAULT NULL,
  `basis_for_usage_and_dosage`     VARCHAR(255) DEFAULT NULL,
  `link_to_usage_and_dosage`       VARCHAR(512) DEFAULT NULL,
  `virulence`                      TEXT         DEFAULT NULL,
  `toxicity_mechanism`             TEXT         DEFAULT NULL,
  `pathological_examination`       TEXT         DEFAULT NULL,
  `crowd_taboo`                    TEXT         DEFAULT NULL,
  `symptom_contraindications`      TEXT         DEFAULT NULL,
  `related_toxic_herbs`            TEXT         DEFAULT NULL,
  `adr`                            TEXT         DEFAULT NULL COMMENT 'Adverse Drug Reactions',
  `typical_cases_of_adr`           TEXT         DEFAULT NULL,
  `clinical_suggestion`            TEXT         DEFAULT NULL,
  `clinical_suggestion_basis`      TEXT         DEFAULT NULL,
  `link_to_clinical_suggestion`    VARCHAR(512) DEFAULT NULL,
  `related_studies`                TEXT         DEFAULT NULL,
  `link_to_related_studies`        VARCHAR(512) DEFAULT NULL,
  `conclusion_of_related_studies`  TEXT         DEFAULT NULL,
  `created_at`                     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`                     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_decoction_name` (`decoction_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鏂瑰墏-鍖栧悎鐗╁叧鑱旇〃
CREATE TABLE `decoction_compound` (
  `id`                INT          NOT NULL AUTO_INCREMENT,
  `decoction_id`      INT          NOT NULL,
  `compound_type`     VARCHAR(255) DEFAULT NULL,
  `compound_name`     VARCHAR(255) NOT NULL,
  `molecular_formula` VARCHAR(255) DEFAULT NULL,
  `cas`               VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_decoction_compound` (`decoction_id`, `compound_name`),
  KEY `idx_compound_name` (`compound_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鏂瑰墏-姣掓€у寲鍚堢墿鍏宠仈琛?

CREATE TABLE `decoction_toxiccompound` (
  `id`                INT          NOT NULL AUTO_INCREMENT,
  `decoction_id`      INT          NOT NULL,
  `record_number`     BIGINT       NOT NULL,
  `compound_type`     VARCHAR(255) DEFAULT NULL,
  `compound_name`     VARCHAR(255) DEFAULT NULL,
  `molecular_formula` VARCHAR(255) DEFAULT NULL,
  `cas`               VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_decoction_toxic` (`decoction_id`, `record_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鏂瑰墏 Meta 鍒嗘瀽鏁版嵁
CREATE TABLE `decoction_meta` (
  `id`                          INT           NOT NULL AUTO_INCREMENT,
  `decoction_id`                INT           NOT NULL,
  `review_number`               INT           NOT NULL,
  `systematic_review`           VARCHAR(255)  DEFAULT NULL,
  `link`                        VARCHAR(512)  DEFAULT NULL,
  `sorting_number`              INT           NOT NULL,
  `index_value`                 VARCHAR(255)  DEFAULT NULL,
  `study`                       VARCHAR(255)  DEFAULT NULL,
  `quality_score`               DECIMAL(6,2)  DEFAULT NULL,
  `quality_evaluation_criteria` VARCHAR(255)  DEFAULT NULL,
  `experimental_events`         DECIMAL(10,4) DEFAULT NULL,
  `experimental_total`          DECIMAL(10,4) DEFAULT NULL,
  `control_events`              DECIMAL(10,4) DEFAULT NULL,
  `control_total`               DECIMAL(10,4) DEFAULT NULL,
  `weight`                      VARCHAR(255)  DEFAULT NULL,
  `or_or_rr`                    DECIMAL(10,4) DEFAULT NULL,
  `ci_95_lower`                 DECIMAL(10,4) DEFAULT NULL,
  `ci_95_upper`                 DECIMAL(10,4) DEFAULT NULL,
  `index_number`                VARCHAR(255)  DEFAULT NULL,
  `p_value`                     DECIMAL(10,4) DEFAULT NULL,
  `i2`                          VARCHAR(255)  DEFAULT NULL,
  `model`                       VARCHAR(255)  DEFAULT NULL,
  `tsa_analysis`                VARCHAR(255)  DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_decoction_meta` (`decoction_id`, `review_number`, `sorting_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鍗曞懗鑽熀纭€琛?

CREATE TABLE `herb_basic` (
  `id`                           INT          NOT NULL AUTO_INCREMENT,
  `herb_name`                    VARCHAR(255) NOT NULL,
  `herb_name_pinyin`             VARCHAR(255) DEFAULT NULL,
  `functionality`                TEXT         DEFAULT NULL,
  `functionality_basis`          TEXT         DEFAULT NULL,
  `link_to_functionality_basis`  VARCHAR(512) DEFAULT NULL,
  `usage_and_dosage`             TEXT         DEFAULT NULL,
  `basis_for_usage_and_dosage`   VARCHAR(255) DEFAULT NULL,
  `link_to_usage_and_dosage`     VARCHAR(512) DEFAULT NULL,
  `virulence`                    TEXT         DEFAULT NULL,
  `toxicity_mechanism`           TEXT         DEFAULT NULL,
  `pathological_examination`     TEXT         DEFAULT NULL,
  `crowd_taboo`                  TEXT         DEFAULT NULL,
  `symptom_contraindications`    TEXT         DEFAULT NULL,
  `adr`                          TEXT         DEFAULT NULL,
  `typical_cases_of_adr`         TEXT         DEFAULT NULL,
  `clinical_suggestion`          TEXT         DEFAULT NULL,
  `clinical_suggestion_basis`    TEXT         DEFAULT NULL,
  `link_to_clinical_suggestion`  VARCHAR(512) DEFAULT NULL,
  `created_at`                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_herb_name` (`herb_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鍗曞懗鑽?姣掓€у寲鍚堢墿鍏宠仈琛?

CREATE TABLE `herb_toxiccompound` (
  `id`                INT          NOT NULL AUTO_INCREMENT,
  `herb_id`           INT          NOT NULL,
  `record_number`     BIGINT       NOT NULL,
  `compound_type`     VARCHAR(255) DEFAULT NULL,
  `compound_name`     VARCHAR(255) DEFAULT NULL,
  `molecular_formula` VARCHAR(255) DEFAULT NULL,
  `cas`               VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_herb_toxic` (`herb_id`, `record_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 瀵硅嵂鍩虹琛?

CREATE TABLE `herb_couplet_basic` (
  `id`                           INT          NOT NULL AUTO_INCREMENT,
  `herb_couplet_name`            VARCHAR(255) NOT NULL,
  `herb_couplet_name_pinyin`     VARCHAR(255) DEFAULT NULL,
  `functionality`                TEXT         DEFAULT NULL,
  `functionality_basis`          TEXT         DEFAULT NULL,
  `link_to_functionality_basis`  VARCHAR(512) DEFAULT NULL,
  `virulence`                    TEXT         DEFAULT NULL,
  `toxicity_mechanism`           TEXT         DEFAULT NULL,
  `pathological_examination`     TEXT         DEFAULT NULL,
  `crowd_taboo`                  TEXT         DEFAULT NULL,
  `symptom_contraindications`    TEXT         DEFAULT NULL,
  `related_toxic_herbs`          TEXT         DEFAULT NULL,
  `adr`                          TEXT         DEFAULT NULL,
  `typical_cases_of_adr`         TEXT         DEFAULT NULL,
  `clinical_suggestion`          TEXT         DEFAULT NULL,
  `clinical_suggestion_basis`    TEXT         DEFAULT NULL,
  `link_to_clinical_suggestion`  VARCHAR(512) DEFAULT NULL,
  `created_at`                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_couplet_name` (`herb_couplet_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 瀵硅嵂-姣掓€у寲鍚堢墿鍏宠仈琛?

CREATE TABLE `herb_couplet_toxiccompound` (
  `id`                INT          NOT NULL AUTO_INCREMENT,
  `couplet_id`        INT          NOT NULL,
  `record_number`     BIGINT       NOT NULL,
  `compound_type`     VARCHAR(255) DEFAULT NULL,
  `compound_name`     VARCHAR(255) DEFAULT NULL,
  `molecular_formula` VARCHAR(255) DEFAULT NULL,
  `cas`               VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_couplet_toxic` (`couplet_id`, `record_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 鍚嶅缁忛獙琛?

CREATE TABLE `expertise` (
  `id`                    INT          NOT NULL AUTO_INCREMENT,
  `herb_id`               INT          NOT NULL,
  `related_article`       VARCHAR(255) DEFAULT NULL,
  `link_article`          VARCHAR(512) DEFAULT NULL,
  `author`                VARCHAR(255) DEFAULT NULL,
  `abstract`              TEXT         DEFAULT NULL,
  `herb_or_decoction`     TEXT         DEFAULT NULL,
  `application_situation` TEXT         DEFAULT NULL,
  `dosage_course_usage`   TEXT         DEFAULT NULL,
  `couplet`               TEXT         DEFAULT NULL,
  `clinical_case`         TEXT         DEFAULT NULL,
  `related_literature`    TEXT         DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_herb_id` (`herb_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- ============================================================================
-- 绗簩閮ㄥ垎: 鏁版嵁杩佺Щ
-- 鏍稿績鎬濊矾: 瀹炰綋琛ㄤ笉鎸囧畾 id 璁?AUTO_INCREMENT 鐢熸垚鏂板€硷紝
--          鍏宠仈琛ㄧ敤瀹炰綋鍚嶇О JOIN 妗ユ帴鏃?ID -> 鏂?ID
-- ============================================================================

-- --------------------------------------------------
-- 1. 鐢ㄦ埛琛?-- --------------------------------------------------
INSERT IGNORE INTO users (username, password, full_name, phone, gender, role, email, created_at)
SELECT username, password, fullName, phone,
       CASE gender
           WHEN 'male'   THEN 'male'
           WHEN 'female' THEN 'female'
           ELSE 'other'
       END,
       email, createdTime
       'user', email, createdTime
FROM ai_medical_db_old.users;


-- --------------------------------------------------
-- 2. 鍒嗗瓙淇℃伅 (淇濈暀 RecordNumber 閬垮厤姣掓€у叧鑱旇〃鏂)
-- --------------------------------------------------
INSERT IGNORE INTO molecular_info (
    record_number, record_title, record_description,
    fda_pharmacology_summary, livertox_summary,
    inchi, inchi_key, smiles,
    molecular_formula, molecular_weight, xlogp3,
    hydrogen_bond_donor_count, hydrogen_bond_acceptor_count,
    rotatable_bond_count, heavy_atom_count
)
SELECT RecordNumber, RecordTitle,
       NULL,
       `FDA Pharmacology Summary`, `LiverTox Summary`,
       InChI, InChIKey, SMILES,
       `Molecular Formula`, `Molecular Weight`, XLogP3,
       `Hydrogen Bond Donor Count`, `Hydrogen Bond Acceptor Count`,
       `Rotatable Bond Count`, `Heavy Atom Count`
FROM ai_medical_db_old.molecular_info
WHERE RecordNumber IS NOT NULL;


-- --------------------------------------------------
-- 3. 璁烘枃琛?-- --------------------------------------------------
INSERT IGNORE INTO papers (title, authors, journal, `year`, abstract, doi, source_db)
SELECT title, authors, journal, `year`, abstract,
       NULLIF(TRIM(doi), ''),
       source_db
FROM ai_medical_db_old.papers;


-- 3b. 璁烘枃鏍囩 (doi+title 妗ユ帴锛屾竻娲楀熬閮?\r)
INSERT IGNORE INTO paper_tags (paper_id, tag)
SELECT p.id, TRIM(BOTH '\r\n\t ' FROM old.tags)
FROM ai_medical_db_old.papers AS old
JOIN papers AS p
  ON NULLIF(TRIM(p.doi), '') = NULLIF(TRIM(old.doi), '')
 AND p.title = old.title
WHERE old.tags IS NOT NULL
  AND TRIM(BOTH '\r\n\t ' FROM old.tags) <> '';


-- --------------------------------------------------
-- 4. 鏂瑰墏鍩虹
-- --------------------------------------------------
INSERT IGNORE INTO decoction_basic (
    decoction_name, decoction_name_pinyin, dosage_form,
    functionality, functionality_basis, link_to_functionality_basis,
    usage_and_dosage, basis_for_usage_and_dosage, link_to_usage_and_dosage,
    virulence, toxicity_mechanism, pathological_examination,
    crowd_taboo, symptom_contraindications, related_toxic_herbs,
    adr, typical_cases_of_adr,
    clinical_suggestion, clinical_suggestion_basis, link_to_clinical_suggestion,
    related_studies, link_to_related_studies, conclusion_of_related_studies
)
SELECT Decoction_Name, Decoction_Name_in_Pinyin, Dosage_Form,
       Functionality, Functionality_Basis, Link_to_Functionality_Basis,
       Usage_and_Dosage, Basis_for_Usage_and_Dosage, Link_to_Usage_and_Dosage,
       Virulence, Toxicity_Mechanism, Pathological_Examination,
       Crowd_Taboo, Symptom_Contraindications, Related_Toxic_Herbs,
       ADR, Typical_Cases_of_ADR,
       Clinical_Suggestion, Clinical_Suggestion_Basis, Link_to_Clinical_Suggestion,
       Related_Studies, Link_to_Related_Studies, Conclusion_of_Related_Studies
FROM ai_medical_db_old.decoction_basic;


-- 4b. 鏂瑰墏-鍖栧悎鐗╁叧鑱?(鍚嶇О妗ユ帴: 鏃?decoction.ID -> 鏂?decoction.id)
INSERT IGNORE INTO decoction_compound (decoction_id, compound_type, compound_name, molecular_formula, cas)
SELECT db.id, dc.Compound_Types, dc.Compound_Name, dc.Molecular_Formula, dc.CAS
FROM ai_medical_db_old.decoction_compound AS dc
JOIN ai_medical_db_old.decoction_basic    AS old_ ON old_.ID = dc.ID
JOIN decoction_basic                      AS db   ON db.decoction_name = old_.Decoction_Name;


-- 4c. 鏂瑰墏-姣掓€у寲鍚堢墿鍏宠仈
INSERT IGNORE INTO decoction_toxiccompound (decoction_id, record_number, compound_type, compound_name, molecular_formula, cas)
SELECT db.id, dt.RecordNumber, dt.Compound_Types, dt.Compound_Name, dt.Molecular_Formula, dt.CAS
FROM ai_medical_db_old.decoction_toxiccompound AS dt
JOIN ai_medical_db_old.decoction_basic        AS old_ ON old_.ID = dt.ID
JOIN decoction_basic                          AS db   ON db.decoction_name = old_.Decoction_Name;


-- 4d. 鏂瑰墏 Meta 鍒嗘瀽鍏宠仈
INSERT IGNORE INTO decoction_meta (
    decoction_id, review_number, systematic_review, link, sorting_number,
    index_value, study, quality_score, quality_evaluation_criteria,
    experimental_events, experimental_total, control_events, control_total,
    weight, or_or_rr, ci_95_lower, ci_95_upper,
    index_number, p_value, i2, model, tsa_analysis
)
SELECT db.id, dm.review_number, dm.Systematic_Review, dm.Link, dm.Sorting_number,
       dm.Index_Value, dm.Study,
       CAST(dm.Quality_Score AS DECIMAL(6,2)),
       dm.Quality_Evaluation_Criteria,
       CAST(dm.Experimental_Events AS DECIMAL(10,4)),
       CAST(dm.Experimental_Total  AS DECIMAL(10,4)),
       CAST(dm.Control_Events      AS DECIMAL(10,4)),
       CAST(dm.Control_Total       AS DECIMAL(10,4)),
       dm.Weight,
       CAST(dm.OR_or_RR     AS DECIMAL(10,4)),
       CAST(dm.`95%CI_lower` AS DECIMAL(10,4)),
       CAST(dm.`95%CI_upper` AS DECIMAL(10,4)),
       dm.Index_number,
       CAST(dm.P            AS DECIMAL(10,4)),
       dm.I2, dm.Model, dm.TSA_analysis
FROM ai_medical_db_old.decoction_meta  AS dm
JOIN ai_medical_db_old.decoction_basic AS old_ ON old_.ID = dm.ID
JOIN decoction_basic                   AS db   ON db.decoction_name = old_.Decoction_Name;


-- --------------------------------------------------
-- 5. 鍗曞懗鑽熀纭€
-- --------------------------------------------------
INSERT IGNORE INTO herb_basic (
    herb_name, herb_name_pinyin, functionality,
    functionality_basis, link_to_functionality_basis,
    usage_and_dosage, basis_for_usage_and_dosage, link_to_usage_and_dosage,
    virulence, toxicity_mechanism, pathological_examination,
    crowd_taboo, symptom_contraindications,
    adr, typical_cases_of_adr,
    clinical_suggestion, clinical_suggestion_basis, link_to_clinical_suggestion
)
SELECT Herb_Name, Herb_Name_in_Pinyin, Functionality,
       Functionality_Basis, Link_to_Functionality_Basis,
       Usage_and_Dosage, Basis_for_Usage_and_Dosage, Link_to_Usage_and_Dosage,
       Virulence, Toxicity_Mechanism, Pathological_Examination,
       Crowd_Taboo, Symptom_Contraindications,
       ADR, Typical_Cases_of_ADR,
       Clinical_Suggestion, Clinical_Suggestion_Basis, Link_to_Clinical_Suggestion
FROM ai_medical_db_old.herb_basic;


-- 5b. 鍗曞懗鑽?姣掓€у寲鍚堢墿鍏宠仈
INSERT IGNORE INTO herb_toxiccompound (herb_id, record_number, compound_type, compound_name, molecular_formula, cas)
SELECT hb.id, ht.RecordNumber, ht.Compound_Types, ht.Compound_Name, ht.Molecular_Formula, ht.CAS
FROM ai_medical_db_old.herb_toxiccompound AS ht
JOIN ai_medical_db_old.herb_basic        AS old_ ON old_.ID = ht.ID
JOIN herb_basic                          AS hb   ON hb.herb_name = old_.Herb_Name;


-- --------------------------------------------------
-- 6. 瀵硅嵂鍩虹
-- --------------------------------------------------
INSERT IGNORE INTO herb_couplet_basic (
    herb_couplet_name, herb_couplet_name_pinyin, functionality,
    functionality_basis, link_to_functionality_basis,
    virulence, toxicity_mechanism, pathological_examination,
    crowd_taboo, symptom_contraindications, related_toxic_herbs,
    adr, typical_cases_of_adr,
    clinical_suggestion, clinical_suggestion_basis, link_to_clinical_suggestion
)
SELECT HerbCouplet_Name, HerbCouplet_Name_in_Pinyin, Functionality,
       Functionality_Basis, Link_to_Functionality_Basis,
       Virulence, Toxicity_Mechanism, Pathological_Examination,
       Crowd_Taboo, Symptom_Contraindications, Related_Toxic_Herbs,
       ADR, Typical_Cases_of_ADR,
       Clinical_Suggestion, Clinical_Suggestion_Basis, Link_to_Clinical_Suggestion
FROM ai_medical_db_old.herb_couplet_basic;


-- 6b. 瀵硅嵂-姣掓€у寲鍚堢墿鍏宠仈
INSERT IGNORE INTO herb_couplet_toxiccompound (couplet_id, record_number, compound_type, compound_name, molecular_formula, cas)
SELECT cb.id, ct.RecordNumber, ct.Compound_Types, ct.Compound_Name, ct.Molecular_Formula, ct.CAS
FROM ai_medical_db_old.herb_couplet_toxiccompound AS ct
JOIN ai_medical_db_old.herb_couplet_basic        AS old_ ON old_.ID = ct.ID
JOIN herb_couplet_basic                          AS cb   ON cb.herb_couplet_name = old_.HerbCouplet_Name;


-- --------------------------------------------------
-- 7. 鍚嶅缁忛獙 (herb_name 妗ユ帴鍒?herb_id)
-- --------------------------------------------------
INSERT IGNORE INTO expertise (
    herb_id, related_article, link_article, author, abstract,
    herb_or_decoction, application_situation, dosage_course_usage,
    couplet, clinical_case, related_literature
)
SELECT hb.id, e.related_article, e.link_article, e.author, e.abstract,
       e.herb_or_decoction, e.application_situation, e.dosage_course_usage,
       e.couplet, e.clinical_case, e.related_literature
FROM ai_medical_db_old.expertise AS e
JOIN herb_basic AS hb ON hb.herb_name = e.herb_name;


-- ============================================================================
-- 绗笁閮ㄥ垎: 娣诲姞澶栭敭绾︽潫 (鏁版嵁杩佸畬鍐嶅姞锛岄伩鍏嶆彃鍏ラ『搴忔姤閿?
-- ============================================================================

SET FOREIGN_KEY_CHECKS = 0;

ALTER TABLE paper_tags
  ADD CONSTRAINT fk_paper_tags_paper
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE;

ALTER TABLE decoction_compound
  ADD CONSTRAINT fk_dc_decoction
  FOREIGN KEY (decoction_id) REFERENCES decoction_basic(id) ON DELETE CASCADE;

ALTER TABLE decoction_toxiccompound
  ADD CONSTRAINT fk_dtc_decoction
  FOREIGN KEY (decoction_id) REFERENCES decoction_basic(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_dtc_molecule
  FOREIGN KEY (record_number) REFERENCES molecular_info(record_number) ON DELETE CASCADE;

ALTER TABLE decoction_meta
  ADD CONSTRAINT fk_dm_decoction
  FOREIGN KEY (decoction_id) REFERENCES decoction_basic(id) ON DELETE CASCADE;

ALTER TABLE herb_toxiccompound
  ADD CONSTRAINT fk_htc_herb
  FOREIGN KEY (herb_id) REFERENCES herb_basic(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_htc_molecule
  FOREIGN KEY (record_number) REFERENCES molecular_info(record_number) ON DELETE CASCADE;

ALTER TABLE herb_couplet_toxiccompound
  ADD CONSTRAINT fk_hctc_couplet
  FOREIGN KEY (couplet_id) REFERENCES herb_couplet_basic(id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_hctc_molecule
  FOREIGN KEY (record_number) REFERENCES molecular_info(record_number) ON DELETE CASCADE;

ALTER TABLE expertise
  ADD CONSTRAINT fk_expertise_herb
  FOREIGN KEY (herb_id) REFERENCES herb_basic(id) ON DELETE CASCADE;

SET FOREIGN_KEY_CHECKS = 1;


-- ============================================================================
-- 绗洓閮ㄥ垎: 鏍稿琛屾暟锛堜笌鏃у簱瀵规瘮锛?-- ============================================================================

SELECT 'users'                      AS tbl, COUNT(*) AS cnt FROM users                       UNION ALL
SELECT 'molecular_info'             AS tbl, COUNT(*) AS cnt FROM molecular_info              UNION ALL
SELECT 'papers'                     AS tbl, COUNT(*) AS cnt FROM papers                      UNION ALL
SELECT 'paper_tags'                 AS tbl, COUNT(*) AS cnt FROM paper_tags                  UNION ALL
SELECT 'decoction_basic'            AS tbl, COUNT(*) AS cnt FROM decoction_basic             UNION ALL
SELECT 'decoction_compound'         AS tbl, COUNT(*) AS cnt FROM decoction_compound          UNION ALL
SELECT 'decoction_meta'             AS tbl, COUNT(*) AS cnt FROM decoction_meta              UNION ALL
SELECT 'decoction_toxiccompound'    AS tbl, COUNT(*) AS cnt FROM decoction_toxiccompound     UNION ALL
SELECT 'herb_basic'                 AS tbl, COUNT(*) AS cnt FROM herb_basic                  UNION ALL
SELECT 'herb_toxiccompound'         AS tbl, COUNT(*) AS cnt FROM herb_toxiccompound          UNION ALL
SELECT 'herb_couplet_basic'         AS tbl, COUNT(*) AS cnt FROM herb_couplet_basic          UNION ALL
SELECT 'herb_couplet_toxiccompound' AS tbl, COUNT(*) AS cnt FROM herb_couplet_toxiccompound  UNION ALL
SELECT 'expertise'                  AS tbl, COUNT(*) AS cnt FROM expertise;
