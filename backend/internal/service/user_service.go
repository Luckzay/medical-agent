package service

import (
	"errors"
	"fmt"

	"medicalagent/internal/model"
	"medicalagent/internal/repository"

	"golang.org/x/crypto/bcrypt"
)

var (
	ErrUserPending  = errors.New("账号正在等待管理员审核")
	ErrUserRejected = errors.New("账号审核未通过")
)

type UserRepository interface {
	GetByUsername(username string) (*model.User, error)
	GetByID(id int) (*model.User, error)
	List(page, pageSize int) ([]model.User, int64, error)
	Create(user *model.User) error
	Update(user *model.User) error
	UpdateStatus(id int, status string) error
	Delete(id int) error
}

type UserService struct {
	repo UserRepository
}

func NewUserService() *UserService { return NewUserServiceWithRepo(repository.NewUserRepo()) }

func NewUserServiceWithRepo(repo UserRepository) *UserService { return &UserService{repo: repo} }

func (s *UserService) Login(username, password string) (*model.UserResponse, error) {
	user, err := s.repo.GetByUsername(username)
	if err != nil {
		return nil, err
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(password)); err != nil {
		return nil, err
	}
	switch user.Status {
	case "", model.UserStatusActive: // Empty tolerates rows read before the status migration.
	case model.UserStatusPending:
		return nil, ErrUserPending
	case model.UserStatusRejected:
		return nil, ErrUserRejected
	default:
		return nil, fmt.Errorf("未知账号状态: %s", user.Status)
	}
	resp := user.ToResponse()
	if resp.Status == "" {
		resp.Status = model.UserStatusActive
	}
	return &resp, nil
}

func (s *UserService) List(page, pageSize int) ([]model.UserResponse, int64, error) {
	users, total, err := s.repo.List(page, pageSize)
	if err != nil {
		return nil, 0, err
	}
	responses := make([]model.UserResponse, len(users))
	for i := range users {
		responses[i] = users[i].ToResponse()
	}
	return responses, total, nil
}

func (s *UserService) Create(user *model.User) (*model.UserResponse, error) {
	if user.Status == "" {
		user.Status = model.UserStatusActive
	}
	if !IsValidUserStatus(user.Status) {
		return nil, fmt.Errorf("无效的用户状态")
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(user.Password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}
	user.Password = string(hash)
	if err := s.repo.Create(user); err != nil {
		return nil, err
	}
	resp := user.ToResponse()
	return &resp, nil
}

func (s *UserService) Update(user *model.User) error {
	existing, err := s.repo.GetByID(user.ID)
	if err != nil {
		return err
	}
	if user.Status == "" {
		user.Status = existing.Status
		if user.Status == "" {
			user.Status = model.UserStatusActive
		}
	}
	if !IsValidUserStatus(user.Status) {
		return fmt.Errorf("无效的用户状态")
	}
	if user.Password != "" {
		hash, err := bcrypt.GenerateFromPassword([]byte(user.Password), bcrypt.DefaultCost)
		if err != nil {
			return err
		}
		user.Password = string(hash)
		return s.repo.Update(user)
	}
	user.Password = existing.Password
	return s.repo.Update(user)
}

func IsValidUserStatus(status string) bool {
	return status == model.UserStatusPending || status == model.UserStatusActive || status == model.UserStatusRejected
}

func ValidateStatusTransition(current, next string, isAdmin bool) error {
	if !IsValidUserStatus(next) {
		return fmt.Errorf("无效的用户状态")
	}
	if isAdmin {
		return nil
	}
	if current == model.UserStatusPending && (next == model.UserStatusActive || next == model.UserStatusRejected) {
		return nil
	}
	return fmt.Errorf("不允许的状态变更")
}

func (s *UserService) UpdateStatus(id int, status string, isAdmin bool) error {
	user, err := s.repo.GetByID(id)
	if err != nil {
		return err
	}
	current := user.Status
	if current == "" {
		current = model.UserStatusActive
	}
	if err := ValidateStatusTransition(current, status, isAdmin); err != nil {
		return err
	}
	return s.repo.UpdateStatus(id, status)
}

func (s *UserService) Delete(id int) error { return s.repo.Delete(id) }
