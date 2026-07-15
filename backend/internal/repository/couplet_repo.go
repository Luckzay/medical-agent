package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type CoupletRepo struct{ db *gorm.DB }

func NewCoupletRepo() *CoupletRepo { return &CoupletRepo{db: DB} }

func (r *CoupletRepo) List(page, pageSize int, keyword string) ([]model.HerbCoupletBasic, int64, error) {
	var list []model.HerbCoupletBasic
	var total int64
	q := r.db.Model(&model.HerbCoupletBasic{})
	if keyword != "" {
		like := "%" + keyword + "%"
		q = q.Where("herb_couplet_name LIKE ? OR herb_couplet_name_pinyin LIKE ? OR virulence LIKE ?",
			like, like, like)
	}
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := q.Order("id ASC").Offset(offset).Limit(pageSize).Find(&list).Error
	return list, total, err
}

func (r *CoupletRepo) GetByID(id int) (*model.HerbCoupletBasic, error) {
	var c model.HerbCoupletBasic
	err := r.db.First(&c, id).Error
	if err != nil {
		return nil, err
	}
	return &c, nil
}

func (r *CoupletRepo) GetToxicCompounds(coupletID int) ([]model.HerbCoupletToxicCompound, error) {
	var list []model.HerbCoupletToxicCompound
	err := r.db.Where("couplet_id = ?", coupletID).Find(&list).Error
	return list, err
}

func (r *CoupletRepo) Create(c *model.HerbCoupletBasic) error {
	return r.db.Create(c).Error
}

func (r *CoupletRepo) Update(c *model.HerbCoupletBasic) error {
	return r.db.Omit("created_at").Save(c).Error
}

func (r *CoupletRepo) Delete(id int) error {
	return r.db.Delete(&model.HerbCoupletBasic{}, id).Error
}
