package repository

import (
	"context"
	"encoding/json"

	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type AgentRunRepository interface {
	Create(ctx context.Context, run *model.AgentRun) error
	GetByRunIDAndUserID(ctx context.Context, runID string, userID int) (*model.AgentRun, error)
	GetByIdempotencyKeyAndUserID(ctx context.Context, key string, userID int) (*model.AgentRun, error)
	UpdateResult(ctx context.Context, runID string, userID int, status string, errorMessage *string, analysisResult, workflow json.RawMessage) error
}

type AgentRunRepo struct{ db *gorm.DB }

func NewAgentRunRepo() *AgentRunRepo { return &AgentRunRepo{db: DB} }

func (r *AgentRunRepo) Create(ctx context.Context, run *model.AgentRun) error {
	return r.db.WithContext(ctx).Create(run).Error
}

func (r *AgentRunRepo) GetByRunIDAndUserID(ctx context.Context, runID string, userID int) (*model.AgentRun, error) {
	var run model.AgentRun
	if err := r.db.WithContext(ctx).Where("run_id = ? AND user_id = ?", runID, userID).First(&run).Error; err != nil {
		return nil, err
	}
	return &run, nil
}

func (r *AgentRunRepo) GetByIdempotencyKeyAndUserID(ctx context.Context, key string, userID int) (*model.AgentRun, error) {
	var run model.AgentRun
	if err := r.db.WithContext(ctx).Where("idempotency_key = ? AND user_id = ?", key, userID).First(&run).Error; err != nil {
		return nil, err
	}
	return &run, nil
}

func (r *AgentRunRepo) UpdateResult(ctx context.Context, runID string, userID int, status string, errorMessage *string, analysisResult, workflow json.RawMessage) error {
	updates := map[string]any{"status": status}
	if errorMessage != nil {
		updates["error_message"] = *errorMessage
	}
	if analysisResult != nil {
		updates["analysis_result"] = analysisResult
	}
	if workflow != nil {
		updates["workflow"] = workflow
	}
	result := r.db.WithContext(ctx).Model(&model.AgentRun{}).
		Where("run_id = ? AND user_id = ?", runID, userID).
		Updates(updates)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}
