package service

import (
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
	return s.repo.List(page, pageSize, keyword)
}

type DecoctionDetail struct {
	*model.DecoctionBasic
	Compounds      []model.DecoctionCompound      `json:"compounds"`
	ToxicCompounds []model.DecoctionToxicCompound  `json:"toxic_compounds"`
	Meta           []model.DecoctionMeta           `json:"meta"`
}

func (s *DecoctionService) GetDetail(id int) (*DecoctionDetail, error) {
	d, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	compounds, _ := s.repo.GetCompounds(id)
	toxic, _ := s.repo.GetToxicCompounds(id)
	meta, _ := s.repo.GetMeta(id)
	return &DecoctionDetail{DecoctionBasic: d, Compounds: compounds, ToxicCompounds: toxic, Meta: meta}, nil
}

func (s *DecoctionService) Create(d *model.DecoctionBasic) error {
	return s.repo.Create(d)
}

func (s *DecoctionService) Update(d *model.DecoctionBasic) error {
	return s.repo.Update(d)
}

func (s *DecoctionService) Delete(id int) error {
	return s.repo.Delete(id)
}
