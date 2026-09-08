-- Iteration 2: 持久化 Python Agent 返回的结构化科研分析结果
ALTER TABLE `agent_runs`
  ADD COLUMN `analysis_result` JSON NULL AFTER `error_message`;
