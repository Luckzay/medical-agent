package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type ExpertiseRepo struct{ db *gorm.DB }

func NewExpertiseRepo() *ExpertiseRepo { return &ExpertiseRepo{db: DB} }

func (r *ExpertiseRepo) List(page, pageSize int, keyword string) ([]model.Expertise, int64, error) {
	var list []model.Expertise
	var total int64
	q := r.db.Model(&model.Expertise{})
	if keyword != "" {
		like := "%" + keyword + "%"
		q = q.Where("author LIKE ? OR related_article LIKE ? OR abstract LIKE ?",
			like, like, like)
	}
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := q.Order("id ASC").Offset(offset).Limit(pageSize).Find(&list).Error
	return list, total, err
}

func (r *ExpertiseRepo) GetByID(id int) (*model.Expertise, error) {
	var e model.Expertise
	err := r.db.First(&e, id).Error
	if err != nil {
		return nil, err
	}
	return &e, nil
}

func (r *ExpertiseRepo) ListByHerbID(herbID int) ([]model.Expertise, error) {
	var list []model.Expertise
	err := r.db.Where("herb_id = ?", herbID).Find(&list).Error
	return list, err
}
