package service

import (
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
	return s.repo.List(page, pageSize, keyword)
}

func (s *ExpertiseService) GetByID(id int) (*model.Expertise, error) {
	return s.repo.GetByID(id)
}
