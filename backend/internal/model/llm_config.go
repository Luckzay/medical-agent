package model

import "time"

type LLMConfig struct {
	ID              uint      `gorm:"primaryKey" json:"-"`
	Provider        string    `gorm:"size:50;not null" json:"provider"`
	BaseURL         string    `gorm:"size:255;not null" json:"base_url"`
	APIKeyEncrypted string    `gorm:"type:text;not null" json:"-"`
	ModelName       string    `gorm:"size:100;not null" json:"model_name"`
	Enabled         bool      `gorm:"index;default:false" json:"enabled"`
	UpdatedBy       int       `gorm:"not null" json:"updated_by"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

func (LLMConfig) TableName() string {
	return "llm_configs"
}

type LLMConfigResponse struct {
	Provider     string    `json:"provider"`
	BaseURL      string    `json:"base_url"`
	ModelName    string    `json:"model_name"`
	Enabled      bool      `json:"enabled"`
	HasAPIKey    bool      `json:"has_api_key"`
	MaskedAPIKey string    `json:"masked_api_key"`
	UpdatedBy    int       `json:"updated_by"`
	UpdatedAt    time.Time `json:"updated_at"`
}
