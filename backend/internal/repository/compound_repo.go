package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type CompoundRepo struct{ db *gorm.DB }

func NewCompoundRepo() *CompoundRepo { return &CompoundRepo{db: DB} }

func (r *CompoundRepo) List(page, pageSize int, keyword string) ([]model.MolecularInfo, int64, error) {
	var list []model.MolecularInfo
	var total int64
	q := r.db.Model(&model.MolecularInfo{})
	if keyword != "" {
		like := "%" + keyword + "%"
		q = q.Where("record_title LIKE ? OR inchi LIKE ? OR inchi_key LIKE ? OR smiles LIKE ? OR molecular_formula LIKE ?",
			like, like, like, like, like)
	}
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := q.Order("record_number ASC").Offset(offset).Limit(pageSize).Find(&list).Error
	return list, total, err
}

func (r *CompoundRepo) GetByRecordNumber(rn int64) (*model.MolecularInfo, error) {
	var m model.MolecularInfo
	err := r.db.First(&m, rn).Error
	if err != nil {
		return nil, err
	}
	return &m, nil
}

func (r *CompoundRepo) Create(m *model.MolecularInfo) error {
	return r.db.Create(m).Error
}

func (r *CompoundRepo) Update(m *model.MolecularInfo) error {
	return r.db.Save(m).Error
}

func (r *CompoundRepo) Delete(rn int64) error {
	return r.db.Delete(&model.MolecularInfo{}, rn).Error
}
