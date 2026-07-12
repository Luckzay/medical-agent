package service

import (
	"medicalagent/internal/model"
	"medicalagent/internal/repository"
)

type CompoundService struct {
	repo *repository.CompoundRepo
}

func NewCompoundService() *CompoundService {
	return &CompoundService{repo: repository.NewCompoundRepo()}
}

func (s *CompoundService) List(page, pageSize int, keyword string) ([]model.MolecularInfo, int64, error) {
	return s.repo.List(page, pageSize, keyword)
}

func (s *CompoundService) GetByRecordNumber(rn int64) (*model.MolecularInfo, error) {
	return s.repo.GetByRecordNumber(rn)
}
