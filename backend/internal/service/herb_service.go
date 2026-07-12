package service

import (
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
	return s.herbRepo.List(page, pageSize, keyword)
}

type HerbDetail struct {
	*model.HerbBasic
	ToxicCompounds []model.HerbToxicCompound `json:"toxic_compounds"`
	Expertises     []model.Expertise         `json:"expertises"`
}

func (s *HerbService) GetDetail(id int) (*HerbDetail, error) {
	h, err := s.herbRepo.GetByID(id)
	if err != nil {
		return nil, err
	}
	compounds, _ := s.herbRepo.GetToxicCompounds(id)
	expertises, _ := s.expertiseRepo.ListByHerbID(id)
	return &HerbDetail{HerbBasic: h, ToxicCompounds: compounds, Expertises: expertises}, nil
}
