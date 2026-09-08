package repository

import (
	"context"
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type LLMConfigRepository interface {
	Get(ctx context.Context) (*model.LLMConfig, error)
	Save(ctx context.Context, config *model.LLMConfig) error
}

type llmConfigRepo struct {
	db *gorm.DB
}

func NewLLMConfigRepo() LLMConfigRepository {
	return &llmConfigRepo{db: DB}
}

func (r *llmConfigRepo) Get(ctx context.Context) (*model.LLMConfig, error) {
	var cfg model.LLMConfig
	err := r.db.WithContext(ctx).First(&cfg, 1).Error
	if err != nil {
		return nil, err
	}
	return &cfg, nil
}

func (r *llmConfigRepo) Save(ctx context.Context, cfg *model.LLMConfig) error {
	cfg.ID = 1
	return r.db.WithContext(ctx).Save(cfg).Error
}
