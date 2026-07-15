package repository

import (
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type UserRepo struct{ db *gorm.DB }

func NewUserRepo() *UserRepo { return &UserRepo{db: DB} }

func (r *UserRepo) GetByUsername(username string) (*model.User, error) {
	var u model.User
	err := r.db.Where("username = ?", username).First(&u).Error
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UserRepo) GetByID(id int) (*model.User, error) {
	var u model.User
	err := r.db.First(&u, id).Error
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UserRepo) List(page, pageSize int) ([]model.User, int64, error) {
	var list []model.User
	var total int64
	if err := r.db.Model(&model.User{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * pageSize
	err := r.db.Order("id ASC").Offset(offset).Limit(pageSize).Find(&list).Error
	return list, total, err
}

func (r *UserRepo) Create(user *model.User) error {
	return r.db.Create(user).Error
}

func (r *UserRepo) Update(user *model.User) error {
	return r.db.Omit("created_at", "updated_at").Save(user).Error
}

func (r *UserRepo) Delete(id int) error {
	return r.db.Delete(&model.User{}, id).Error
}
