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

func (s *CompoundService) Create(m *model.MolecularInfo) error {
	return s.repo.Create(m)
}

func (s *CompoundService) Update(m *model.MolecularInfo) error {
	return s.repo.Update(m)
}

func (s *CompoundService) Delete(rn int64) error {
	return s.repo.Delete(rn)
}
