package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type DecoctionRepo struct{ db *gorm.DB }

func NewDecoctionRepo() *DecoctionRepo { return &DecoctionRepo{db: DB} }

func (r *DecoctionRepo) List(page, pageSize int, keyword string) ([]model.DecoctionBasic, int64, error) {
	var list []model.DecoctionBasic
	var total int64
	q := r.db.Model(&model.DecoctionBasic{})
	if keyword != "" {
		like := "%" + keyword + "%"
		q = q.Where("decoction_name LIKE ? OR decoction_name_pinyin LIKE ? OR virulence LIKE ?",
			like, like, like)
	}
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := q.Order("id ASC").Offset(offset).Limit(pageSize).Find(&list).Error
	return list, total, err
}

func (r *DecoctionRepo) GetByID(id int) (*model.DecoctionBasic, error) {
	var d model.DecoctionBasic
	err := r.db.First(&d, id).Error
	if err != nil {
		return nil, err
	}
	return &d, nil
}

func (r *DecoctionRepo) GetCompounds(decoctionID int) ([]model.DecoctionCompound, error) {
	var list []model.DecoctionCompound
	err := r.db.Where("decoction_id = ?", decoctionID).Find(&list).Error
	return list, err
}

func (r *DecoctionRepo) GetToxicCompounds(decoctionID int) ([]model.DecoctionToxicCompound, error) {
	var list []model.DecoctionToxicCompound
	err := r.db.Where("decoction_id = ?", decoctionID).Find(&list).Error
	return list, err
}

func (r *DecoctionRepo) GetMeta(decoctionID int) ([]model.DecoctionMeta, error) {
	var list []model.DecoctionMeta
	err := r.db.Where("decoction_id = ?", decoctionID).Order("review_number ASC, sorting_number ASC").Find(&list).Error
	return list, err
}
