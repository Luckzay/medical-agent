package service

import (
	"context"
	"fmt"
	"time"

	"medicalagent/internal/cache"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type HerbService struct {
	herbRepo      *repository.HerbRepo
	expertiseRepo *repository.ExpertiseRepo
}

func NewHerbService() *HerbService {
	return &HerbService{
		herbRepo:      repository.NewHerbRepo(),
		expertiseRepo: repository.NewExpertiseRepo(),
	}
}

func (s *HerbService) List(page, pageSize int, keyword string) ([]model.HerbBasic, int64, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("herb:list:%d:%d:%s", page, pageSize, keyword)

	var cached struct {
		List  []model.HerbBasic `json:"list"`
		Total int64             `json:"total"`
	}
	if cache.Get(ctx, cacheKey, &cached) {
		return cached.List, cached.Total, nil
	}

	list, total, err := s.herbRepo.List(page, pageSize, keyword)
	if err != nil {
		return nil, 0, err
	}

	cache.Set(ctx, cacheKey, map[string]any{"list": list, "total": total}, 5*time.Minute)
	return list, total, nil
}

type HerbDetail struct {
	*model.HerbBasic
	ToxicCompounds []model.HerbToxicCompound `json:"toxic_compounds"`
	Expertises     []model.Expertise         `json:"expertises"`
}

func (s *HerbService) GetDetail(id int) (*HerbDetail, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("herb:detail:%d", id)

	var cached HerbDetail
	if cache.Get(ctx, cacheKey, &cached) && cached.HerbBasic != nil {
		return &cached, nil
	}

	h, err := s.herbRepo.GetByID(id)
	if err != nil {
		return nil, err
	}
	compounds, _ := s.herbRepo.GetToxicCompounds(id)
	expertises, _ := s.expertiseRepo.ListByHerbID(id)

	detail := &HerbDetail{HerbBasic: h, ToxicCompounds: compounds, Expertises: expertises}
	cache.Set(ctx, cacheKey, detail, 10*time.Minute)
	return detail, nil
}

func (s *HerbService) Create(h *model.HerbBasic) error {
	err := s.herbRepo.Create(h)
	if err == nil {
		cache.DelPattern(context.Background(), "herb:list:*")
	}
	return err
}

func (s *HerbService) Update(h *model.HerbBasic) error {
	err := s.herbRepo.Update(h)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("herb:detail:%d", h.ID))
		cache.DelPattern(ctx, "herb:list:*")
	}
	return err
}

func (s *HerbService) Delete(id int) error {
	err := s.herbRepo.Delete(id)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("herb:detail:%d", id))
		cache.DelPattern(ctx, "herb:list:*")
	}
	return err
}
