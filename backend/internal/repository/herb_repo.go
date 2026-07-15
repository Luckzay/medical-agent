package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type HerbRepo struct{ db *gorm.DB }

func NewHerbRepo() *HerbRepo { return &HerbRepo{db: DB} }

func (r *HerbRepo) List(page, pageSize int, keyword string) ([]model.HerbBasic, int64, error) {
	var herbs []model.HerbBasic
	var total int64
	q := r.db.Model(&model.HerbBasic{})
	if keyword != "" {
		like := "%" + keyword + "%"
		q = q.Where("herb_name LIKE ? OR herb_name_pinyin LIKE ? OR virulence LIKE ?",
			like, like, like)
	}
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := q.Order("id ASC").Offset(offset).Limit(pageSize).Find(&herbs).Error
	return herbs, total, err
}

func (r *HerbRepo) GetByID(id int) (*model.HerbBasic, error) {
	var h model.HerbBasic
	err := r.db.First(&h, id).Error
	if err != nil {
		return nil, err
	}
	return &h, nil
}

func (r *HerbRepo) GetToxicCompounds(herbID int) ([]model.HerbToxicCompound, error) {
	var compounds []model.HerbToxicCompound
	err := r.db.Where("herb_id = ?", herbID).Find(&compounds).Error
	return compounds, err
}

func (r *HerbRepo) Create(h *model.HerbBasic) error {
	return r.db.Create(h).Error
}

func (r *HerbRepo) Update(h *model.HerbBasic) error {
	return r.db.Omit("created_at").Save(h).Error
}

func (r *HerbRepo) Delete(id int) error {
	return r.db.Delete(&model.HerbBasic{}, id).Error
}
