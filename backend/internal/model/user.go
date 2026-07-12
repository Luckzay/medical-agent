package model

import "time"

// User is the database entity. Password has json:"password" so it can be
// deserialized from login/registration requests, but it must never appear in
// a response. Use ToResponse() to get a safe UserResponse for output.
type User struct {
	ID        int       `gorm:"primaryKey;autoIncrement" json:"id"`
	Username  string    `gorm:"unique;not null;size:50" json:"username"`
	Password  string    `gorm:"not null;size:255" json:"password"`
	FullName  string    `gorm:"not null;size:50" json:"full_name"`
	Phone     string    `gorm:"not null;size:20" json:"phone"`
	Gender    string    `gorm:"not null;default:other;type:enum('male','female','other')" json:"gender"`
	Email     string    `gorm:"unique;not null;size:100" json:"email"`
	Role      string    `gorm:"not null;default:user;type:enum('admin','user')" json:"role"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

func (User) TableName() string { return "users" }

// UserResponse is the safe output DTO — no Password field, impossible to leak.
type UserResponse struct {
	ID        int       `json:"id"`
	Username  string    `json:"username"`
	FullName  string    `json:"full_name"`
	Phone     string    `json:"phone"`
	Gender    string    `json:"gender"`
	Email     string    `json:"email"`
	Role      string    `json:"role"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

func (u *User) ToResponse() UserResponse {
	return UserResponse{
		ID:        u.ID,
		Username:  u.Username,
		FullName:  u.FullName,
		Phone:     u.Phone,
		Gender:    u.Gender,
		Email:     u.Email,
		Role:      u.Role,
		CreatedAt: u.CreatedAt,
		UpdatedAt: u.UpdatedAt,
	}
}
