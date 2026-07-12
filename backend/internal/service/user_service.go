package service

import (
	"medicalagent/internal/model"
	"medicalagent/internal/repository"

	"golang.org/x/crypto/bcrypt"
)

type UserService struct {
	repo *repository.UserRepo
}

func NewUserService() *UserService { return &UserService{repo: repository.NewUserRepo()} }

func (s *UserService) Login(username, password string) (*model.UserResponse, error) {
	user, err := s.repo.GetByUsername(username)
	if err != nil {
		return nil, err
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(password)); err != nil {
		return nil, err
	}
	resp := user.ToResponse()
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
	if user.Password != "" {
		hash, err := bcrypt.GenerateFromPassword([]byte(user.Password), bcrypt.DefaultCost)
		if err != nil {
			return err
		}
		user.Password = string(hash)
		return s.repo.Update(user)
	}

	// Password not provided — preserve the existing one from DB.
	existing, err := s.repo.GetByID(user.ID)
	if err != nil {
		return err
	}
	user.Password = existing.Password
	return s.repo.Update(user)
}

func (s *UserService) Delete(id int) error {
	return s.repo.Delete(id)
}
