-- User approval workflow and additional bootstrap administrators.
-- MySQL 8.4; safe to re-run. Existing account passwords are not reset.
USE `ai_medical_db`;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'affiliation'),
  'SELECT 1',
  'ALTER TABLE `users` ADD COLUMN `affiliation` VARCHAR(150) NOT NULL DEFAULT '''' AFTER `full_name`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'professional_title'),
  'SELECT 1',
  'ALTER TABLE `users` ADD COLUMN `professional_title` VARCHAR(100) NOT NULL DEFAULT '''' AFTER `affiliation`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'email_consent'),
  'SELECT 1',
  'ALTER TABLE `users` ADD COLUMN `email_consent` BOOLEAN NOT NULL DEFAULT FALSE AFTER `email`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'status'),
  'SELECT 1',
  'ALTER TABLE `users` ADD COLUMN `status` ENUM(''pending'',''active'',''rejected'') NOT NULL DEFAULT ''active'' AFTER `role`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- The DEFAULT preserves compatibility for all rows created before approval existed.
UPDATE `users` SET `status` = 'active' WHERE `status` IS NULL OR `status` = '';

INSERT INTO `users`
  (`username`, `password`, `full_name`, `affiliation`, `professional_title`, `phone`, `gender`, `role`, `status`, `email`, `email_consent`)
VALUES
  ('admin',  '$2y$10$HJ7hJVRYZFTxdaznM7OMz.FF.iAPvnajhTchIoay6VyEM0PP3su06', '系统管理员1', '示例医疗机构', '系统管理员', '00000000001', 'other', 'admin', 'active', 'admin@example.com', TRUE),
  ('admin2', '$2y$10$HJ7hJVRYZFTxdaznM7OMz.FF.iAPvnajhTchIoay6VyEM0PP3su06', '系统管理员2', '示例医疗机构', '系统管理员', '00000000002', 'other', 'admin', 'active', 'admin2@example.com', TRUE),
  ('admin3', '$2y$10$HJ7hJVRYZFTxdaznM7OMz.FF.iAPvnajhTchIoay6VyEM0PP3su06', '系统管理员3', '示例医疗机构', '系统管理员', '00000000003', 'other', 'admin', 'active', 'admin3@example.com', TRUE),
  ('admin4', '$2y$10$HJ7hJVRYZFTxdaznM7OMz.FF.iAPvnajhTchIoay6VyEM0PP3su06', '系统管理员4', '示例医疗机构', '系统管理员', '00000000004', 'other', 'admin', 'active', 'admin4@example.com', TRUE),
  ('admin5', '$2y$10$HJ7hJVRYZFTxdaznM7OMz.FF.iAPvnajhTchIoay6VyEM0PP3su06', '系统管理员5', '示例医疗机构', '系统管理员', '00000000005', 'other', 'admin', 'active', 'admin5@example.com', TRUE)
ON DUPLICATE KEY UPDATE
  `role` = 'admin',
  `status` = 'active',
  `affiliation` = IF(`affiliation` = '', VALUES(`affiliation`), `affiliation`),
  `professional_title` = IF(`professional_title` = '', VALUES(`professional_title`), `professional_title`),
  `email_consent` = TRUE;

UPDATE `users` SET `status` = 'active' WHERE `username` = 'user';
