package model

import "time"

const (
	UserStatusPending  = "pending"
	UserStatusActive   = "active"
	UserStatusRejected = "rejected"
)

// User is the database entity. Password may be deserialized from requests but
// must never be serialized in a response; use ToResponse for output.
type User struct {
	ID                int       `gorm:"primaryKey;autoIncrement" json:"id"`
	Username          string    `gorm:"unique;not null;size:50" json:"username"`
	Password          string    `gorm:"not null;size:255" json:"password"`
	FullName          string    `gorm:"not null;size:50" json:"full_name"`
	Affiliation       string    `gorm:"not null;default:'';size:150" json:"affiliation"`
	ProfessionalTitle string    `gorm:"not null;default:'';size:100" json:"professional_title"`
	Phone             string    `gorm:"not null;size:20" json:"phone"`
	Gender            string    `gorm:"not null;default:other;type:enum('male','female','other')" json:"gender"`
	Email             string    `gorm:"unique;not null;size:100" json:"email"`
	EmailConsent      bool      `gorm:"not null;default:false" json:"email_consent"`
	Role              string    `gorm:"not null;default:user;type:enum('admin','user')" json:"role"`
	Status            string    `gorm:"not null;default:active;type:enum('pending','active','rejected')" json:"status"`
	CreatedAt         time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt         time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

func (User) TableName() string { return "users" }

type UserResponse struct {
	ID                int       `json:"id"`
	Username          string    `json:"username"`
	FullName          string    `json:"full_name"`
	Affiliation       string    `json:"affiliation"`
	ProfessionalTitle string    `json:"professional_title"`
	Phone             string    `json:"phone"`
	Gender            string    `json:"gender"`
	Email             string    `json:"email"`
	EmailConsent      bool      `json:"email_consent"`
	Role              string    `json:"role"`
	Status            string    `json:"status"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}

func (u *User) ToResponse() UserResponse {
	return UserResponse{
		ID: u.ID, Username: u.Username, FullName: u.FullName,
		Affiliation: u.Affiliation, ProfessionalTitle: u.ProfessionalTitle,
		Phone: u.Phone, Gender: u.Gender, Email: u.Email,
		EmailConsent: u.EmailConsent, Role: u.Role, Status: u.Status,
		CreatedAt: u.CreatedAt, UpdatedAt: u.UpdatedAt,
	}
}
