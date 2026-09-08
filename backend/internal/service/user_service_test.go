package service

import (
	"errors"
	"testing"

	"medicalagent/internal/model"

	"golang.org/x/crypto/bcrypt"
)

type fakeUserRepo struct {
	user          *model.User
	updatedStatus string
}

func (f *fakeUserRepo) GetByUsername(string) (*model.User, error) { return f.user, nil }
func (f *fakeUserRepo) GetByID(int) (*model.User, error)          { return f.user, nil }
func (f *fakeUserRepo) List(int, int) ([]model.User, int64, error) {
	return nil, 0, nil
}
func (f *fakeUserRepo) Create(*model.User) error { return nil }
func (f *fakeUserRepo) Update(*model.User) error { return nil }
func (f *fakeUserRepo) UpdateStatus(_ int, status string) error {
	f.updatedStatus = status
	return nil
}
func (f *fakeUserRepo) Delete(int) error { return nil }

func passwordHash(t *testing.T) string {
	t.Helper()
	hash, err := bcrypt.GenerateFromPassword([]byte("secret"), bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}
	return string(hash)
}

func TestLoginReturnsDistinctApprovalErrors(t *testing.T) {
	for _, tt := range []struct {
		status string
		want   error
	}{
		{model.UserStatusPending, ErrUserPending},
		{model.UserStatusRejected, ErrUserRejected},
	} {
		t.Run(tt.status, func(t *testing.T) {
			repo := &fakeUserRepo{user: &model.User{Password: passwordHash(t), Status: tt.status}}
			_, err := NewUserServiceWithRepo(repo).Login("user", "secret")
			if !errors.Is(err, tt.want) {
				t.Fatalf("Login() error = %v, want %v", err, tt.want)
			}
		})
	}
}

func TestValidateStatusTransition(t *testing.T) {
	if err := ValidateStatusTransition(model.UserStatusPending, model.UserStatusActive, false); err != nil {
		t.Fatalf("pending -> active should be valid: %v", err)
	}
	if err := ValidateStatusTransition(model.UserStatusPending, model.UserStatusRejected, false); err != nil {
		t.Fatalf("pending -> rejected should be valid: %v", err)
	}
	if err := ValidateStatusTransition(model.UserStatusActive, model.UserStatusPending, false); err == nil {
		t.Fatal("non-admin active -> pending should be rejected")
	}
	if err := ValidateStatusTransition(model.UserStatusActive, model.UserStatusPending, true); err != nil {
		t.Fatalf("admin adjustment should be valid: %v", err)
	}
	if err := ValidateStatusTransition(model.UserStatusPending, "disabled", true); err == nil {
		t.Fatal("unknown status should always be rejected")
	}
}

func TestUpdateStatusUsesValidatedValue(t *testing.T) {
	repo := &fakeUserRepo{user: &model.User{Status: model.UserStatusPending}}
	if err := NewUserServiceWithRepo(repo).UpdateStatus(3, model.UserStatusActive, true); err != nil {
		t.Fatal(err)
	}
	if repo.updatedStatus != model.UserStatusActive {
		t.Fatalf("updated status = %q", repo.updatedStatus)
	}
}
