package service

import (
	"context"
	"fmt"
	"time"

	"medicalagent/internal/cache"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type PaperService struct {
	repo *repository.PaperRepo
}

func NewPaperService() *PaperService {
	return &PaperService{repo: repository.NewPaperRepo()}
}

func (s *PaperService) List(page, pageSize int, keyword string) ([]model.Paper, int64, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("paper:list:%d:%d:%s", page, pageSize, keyword)

	var cached struct {
		List  []model.Paper `json:"list"`
		Total int64         `json:"total"`
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

type PaperDetail struct {
	*model.Paper
	Tags []model.PaperTag `json:"tags"`
}

func (s *PaperService) GetDetail(id int) (*PaperDetail, error) {
	ctx := context.Background()
	cacheKey := fmt.Sprintf("paper:detail:%d", id)

	var cached PaperDetail
	if cache.Get(ctx, cacheKey, &cached) && cached.Paper != nil {
		return &cached, nil
	}

	p, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	tags, _ := s.repo.GetTags(id)
	detail := &PaperDetail{Paper: p, Tags: tags}
	cache.Set(ctx, cacheKey, detail, 10*time.Minute)
	return detail, nil
}

func (s *PaperService) Create(p *model.Paper) error {
	err := s.repo.Create(p)
	if err == nil {
		cache.DelPattern(context.Background(), "paper:list:*")
	}
	return err
}

func (s *PaperService) Update(p *model.Paper) error {
	err := s.repo.Update(p)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("paper:detail:%d", p.ID))
		cache.DelPattern(ctx, "paper:list:*")
	}
	return err
}

func (s *PaperService) Delete(id int) error {
	err := s.repo.Delete(id)
	if err == nil {
		ctx := context.Background()
		cache.Del(ctx, fmt.Sprintf("paper:detail:%d", id))
		cache.DelPattern(ctx, "paper:list:*")
	}
	return err
}
