-- Iteration 1: Agent Run 最小链路
-- 本迁移用于显式部署和审计；Go 服务也会通过 GORM AutoMigrate 补齐缺失表和字段。

CREATE TABLE IF NOT EXISTS `agent_runs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `run_id` VARCHAR(64) NOT NULL,
  `user_id` INT NOT NULL,
  `trace_id` VARCHAR(64) NOT NULL,
  `idempotency_key` VARCHAR(255) NULL,
  `request_hash` VARCHAR(64) NOT NULL,
  `herbs_json` JSON NOT NULL,
  `research_goal` TEXT NOT NULL,
  `status` VARCHAR(20) NOT NULL,
  `error_message` TEXT NOT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_agent_runs_run_id` (`run_id`),
  UNIQUE KEY `idx_agent_runs_user_idempotency` (`user_id`, `idempotency_key`),
  KEY `idx_agent_runs_user_id` (`user_id`),
  KEY `idx_agent_runs_trace_id` (`trace_id`),
  KEY `idx_agent_runs_status` (`status`),
  CONSTRAINT `fk_agent_runs_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
