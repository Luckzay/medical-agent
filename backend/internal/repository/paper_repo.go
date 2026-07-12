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

func (r *PaperRepo) Create(p *model.Paper) error {
	return r.db.Create(p).Error
}

func (r *PaperRepo) Update(p *model.Paper) error {
	return r.db.Save(p).Error
}

func (r *PaperRepo) Delete(id int) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("paper_id = ?", id).Delete(&model.PaperTag{}).Error; err != nil {
			return err
		}
		return tx.Delete(&model.Paper{}, id).Error
	})
}
