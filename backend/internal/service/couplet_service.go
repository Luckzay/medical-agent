package service

import (
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
	return s.repo.List(page, pageSize, keyword)
}

type CoupletDetail struct {
	*model.HerbCoupletBasic
	ToxicCompounds []model.HerbCoupletToxicCompound `json:"toxic_compounds"`
}

func (s *CoupletService) GetDetail(id int) (*CoupletDetail, error) {
	c, err := s.repo.GetByID(id)
	if err != nil {
		return nil, err
	}
	compounds, _ := s.repo.GetToxicCompounds(id)
	return &CoupletDetail{HerbCoupletBasic: c, ToxicCompounds: compounds}, nil
}
