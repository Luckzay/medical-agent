package service

import (
	"context"
	"fmt"
	"time"

	"medicalagent/internal/cache"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type DecoctionService struct {
	repo *repository.DecoctionRepo
}

func NewDecoctionService() *DecoctionService {
	return &DecoctionService{repo: repository.NewDecoctionRepo()}
}

func (s *DecoctionService) List(page, pageSize int, keyword string) ([]model.DecoctionBasic, int64, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("decoction:list:%d:%d:%s", page, pageSize, keyword)

	var cached struct {
		List  []model.DecoctionBasic `json:"list"`
		Total int64                  `json:"total"`
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

type DecoctionDetail struct {
	*model.DecoctionBasic
	Compounds      []model.DecoctionCompound      `json:"compounds"`
	ToxicCompounds []model.DecoctionToxicCompound `json:"toxic_compounds"`
	Meta           []model.DecoctionMeta          `json:"meta"`
}

func (s *DecoctionService) GetDetail(id int) (*DecoctionDetail, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("decoction:detail:%d", id)

	var cached DecoctionDetail
	if cache.Get(ctx, cacheKey, &cached) && cached.DecoctionBasic != nil {
		return &cached, nil
	}

	d, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	compounds, _ := s.repo.GetCompounds(id)
	toxic, _ := s.repo.GetToxicCompounds(id)
	meta, _ := s.repo.GetMeta(id)
	detail := &DecoctionDetail{DecoctionBasic: d, Compounds: compounds, ToxicCompounds: toxic, Meta: meta}
	cache.Set(ctx, cacheKey, detail, 10*time.Minute)
	return detail, nil
}

func (s *DecoctionService) Create(d *model.DecoctionBasic) error {
	err := s.repo.Create(d)
	if err == nil {
		cache.DelPattern(context.Background(), "decoction:list:*")
	}
	return err
}

func (s *DecoctionService) Update(d *model.DecoctionBasic) error {
	err := s.repo.Update(d)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("decoction:detail:%d", d.ID))
		cache.DelPattern(ctx, "decoction:list:*")
	}
	return err
}

func (s *DecoctionService) Delete(id int) error {
	err := s.repo.Delete(id)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("decoction:detail:%d", id))
		cache.DelPattern(ctx, "decoction:list:*")
	}
	return err
}
