package service

import (
	"context"
	"fmt"
	"time"

	"medicalagent/internal/cache"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type ExpertiseService struct {
	repo *repository.ExpertiseRepo
}

func NewExpertiseService() *ExpertiseService {
	return &ExpertiseService{repo: repository.NewExpertiseRepo()}
}

func (s *ExpertiseService) List(page, pageSize int, keyword string) ([]model.Expertise, int64, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("expertise:list:%d:%d:%s", page, pageSize, keyword)

	var cached struct {
		List  []model.Expertise `json:"list"`
		Total int64             `json:"total"`
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

func (s *ExpertiseService) GetByID(id int) (*model.Expertise, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("expertise:detail:%d", id)

	var cached model.Expertise
	if cache.Get(ctx, cacheKey, &cached) && cached.ID != 0 {
		return &cached, nil
	}

	item, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	cache.Set(ctx, cacheKey, item, 10*time.Minute)
	return item, nil
}

func (s *ExpertiseService) Create(e *model.Expertise) error {
	err := s.repo.Create(e)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("herb:detail:%d", e.HerbID))
		cache.DelPattern(ctx, "expertise:list:*")
	}
	return err
}

func (s *ExpertiseService) Update(e *model.Expertise) error {
	existing, _ := s.repo.GetByID(e.ID)
	err := s.repo.Update(e)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("expertise:detail:%d", e.ID))
		cache.Del(ctx, fmt.Sprintf("herb:detail:%d", e.HerbID))
		if existing != nil && existing.HerbID != e.HerbID {
			cache.Del(ctx, fmt.Sprintf("herb:detail:%d", existing.HerbID))
		}
		cache.DelPattern(ctx, "expertise:list:*")
	}
	return err
}

func (s *ExpertiseService) Delete(id int) error {
	existing, _ := s.repo.GetByID(id)
	err := s.repo.Delete(id)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("expertise:detail:%d", id))
		if existing != nil {
			cache.Del(ctx, fmt.Sprintf("herb:detail:%d", existing.HerbID))
		}
		cache.DelPattern(ctx, "expertise:list:*")
	}
	return err
}
