package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type PaperRepo struct{ db *gorm.DB }

func NewPaperRepo() *PaperRepo { return &PaperRepo{db: DB} }

func (r *PaperRepo) List(page, pageSize int, keyword string) ([]model.Paper, int64, error) {
	var list []model.Paper
	var total int64
	q := r.db.Model(&model.Paper{})
	if keyword != "" {
		like := "%" + keyword + "%"
		q = q.Where("title LIKE ? OR authors LIKE ? OR journal LIKE ? OR abstract LIKE ?",
			like, like, like, like)
	}
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := q.Order("year DESC, id DESC").Offset(offset).Limit(pageSize).Find(&list).Error
	return list, total, err
}

func (r *PaperRepo) GetByID(id int) (*model.Paper, error) {
	var p model.Paper
	err := r.db.First(&p, id).Error
	if err != nil {
		return nil, err
	}
	return &p, nil
}

func (r *PaperRepo) GetTags(paperID int) ([]model.PaperTag, error) {
	var tags []model.PaperTag
	err := r.db.Where("paper_id = ?", paperID).Find(&tags).Error
	return tags, err
}
