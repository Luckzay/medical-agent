package service

import (
	"context"
	"fmt"
	"time"

	"medicalagent/internal/cache"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type CoupletService struct {
	repo *repository.CoupletRepo
}

func NewCoupletService() *CoupletService {
	return &CoupletService{repo: repository.NewCoupletRepo()}
}

func (s *CoupletService) List(page, pageSize int, keyword string) ([]model.HerbCoupletBasic, int64, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("couplet:list:%d:%d:%s", page, pageSize, keyword)

	var cached struct {
		List  []model.HerbCoupletBasic `json:"list"`
		Total int64                    `json:"total"`
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

type CoupletDetail struct {
	*model.HerbCoupletBasic
	ToxicCompounds []model.HerbCoupletToxicCompound `json:"toxic_compounds"`
}

func (s *CoupletService) GetDetail(id int) (*CoupletDetail, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("couplet:detail:%d", id)

	var cached CoupletDetail
	if cache.Get(ctx, cacheKey, &cached) && cached.HerbCoupletBasic != nil {
		return &cached, nil
	}

	c, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	compounds, _ := s.repo.GetToxicCompounds(id)
	detail := &CoupletDetail{HerbCoupletBasic: c, ToxicCompounds: compounds}
	cache.Set(ctx, cacheKey, detail, 10*time.Minute)
	return detail, nil
}

func (s *CoupletService) Create(c *model.HerbCoupletBasic) error {
	err := s.repo.Create(c)
	if err == nil {
		cache.DelPattern(context.Background(), "couplet:list:*")
	}
	return err
}

func (s *CoupletService) Update(c *model.HerbCoupletBasic) error {
	err := s.repo.Update(c)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("couplet:detail:%d", c.ID))
		cache.DelPattern(ctx, "couplet:list:*")
	}
	return err
}

func (s *CoupletService) Delete(id int) error {
	err := s.repo.Delete(id)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("couplet:detail:%d", id))
		cache.DelPattern(ctx, "couplet:list:*")
	}
	return err
}
