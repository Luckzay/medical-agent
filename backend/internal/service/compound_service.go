package service

import (
	"context"
	"fmt"
	"time"

	"medicalagent/internal/cache"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type CompoundService struct {
	repo *repository.CompoundRepo
}

func NewCompoundService() *CompoundService {
	return &CompoundService{repo: repository.NewCompoundRepo()}
}

func (s *CompoundService) List(page, pageSize int, keyword string) ([]model.MolecularInfo, int64, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("compound:list:%d:%d:%s", page, pageSize, keyword)

	var cached struct {
		List  []model.MolecularInfo `json:"list"`
		Total int64                 `json:"total"`
	}
	if cache.Get(ctx, cacheKey, &cached) {
		return cached.List, cached.Total, nil
	}

	list, total, err := s.repo.List(page, pageSize, keyword)
	if err != nil {
		return nil, 0, err
	}
	cache.Set(ctx, cacheKey, map[string]any{"list": list, "total": total}, 5*time.Minute)
	return list, total, nil
}

func (s *CompoundService) GetByRecordNumber(rn int64) (*model.MolecularInfo, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("compound:detail:%d", rn)

	var cached model.MolecularInfo
	if cache.Get(ctx, cacheKey, &cached) && cached.RecordNumber != 0 {
		return &cached, nil
	}

	item, err := s.repo.GetByRecordNumber(rn)
	if err != nil {
		return nil, err
	}
	cache.Set(ctx, cacheKey, item, 10*time.Minute)
	return item, nil
}

func (s *CompoundService) Create(m *model.MolecularInfo) error {
	err := s.repo.Create(m)
	if err == nil {
		cache.DelPattern(context.Background(), "compound:list:*")
	}
	return err
}

func (s *CompoundService) Update(m *model.MolecularInfo) error {
	err := s.repo.Update(m)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("compound:detail:%d", m.RecordNumber))
		cache.DelPattern(ctx, "compound:list:*")
	}
	return err
}

func (s *CompoundService) Delete(rn int64) error {
	err := s.repo.Delete(rn)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("compound:detail:%d", rn))
		cache.DelPattern(ctx, "compound:list:*")
	}
	return err
}
