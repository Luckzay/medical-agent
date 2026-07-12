package service

import (
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
	return s.repo.List(page, pageSize, keyword)
}

type PaperDetail struct {
	*model.Paper
	Tags []model.PaperTag `json:"tags"`
}

func (s *PaperService) GetDetail(id int) (*PaperDetail, error) {
	p, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	tags, _ := s.repo.GetTags(id)
	return &PaperDetail{Paper: p, Tags: tags}, nil
}

func (s *PaperService) Create(p *model.Paper) error {
	return s.repo.Create(p)
}

func (s *PaperService) Update(p *model.Paper) error {
	return s.repo.Update(p)
}

func (s *PaperService) Delete(id int) error {
	return s.repo.Delete(id)
}
