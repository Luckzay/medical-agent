-- Iteration 3: 持久化 Python Agent 返回的工作流状态
ALTER TABLE `agent_runs`
  ADD COLUMN `workflow` JSON NULL AFTER `analysis_result`;
