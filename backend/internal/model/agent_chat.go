package model

import (
	"encoding/json"
	"time"
)

const (
	AgentChatRoleUser      = "user"
	AgentChatRoleAssistant = "assistant"
	AgentChatStatusPending = "pending"
	AgentChatStatusRunning = "running"
	AgentChatStatusDone    = "completed"
	AgentChatStatusFailed  = "failed"
)

type AgentSession struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	UserID    int       `gorm:"not null;index:idx_agent_sessions_user_updated" json:"-"`
	Title     string    `gorm:"size:255;not null" json:"title"`
	CreatedAt time.Time `gorm:"not null;autoCreateTime" json:"created_at"`
	UpdatedAt time.Time `gorm:"not null;autoUpdateTime;index:idx_agent_sessions_user_updated" json:"updated_at"`
}

func (AgentSession) TableName() string { return "agent_sessions" }

type AgentChatMessage struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	SessionID uint      `gorm:"not null;index:idx_agent_chat_messages_session_created" json:"session_id"`
	TurnID    *string   `gorm:"size:64;index" json:"turn_id,omitempty"`
	Role      string    `gorm:"size:16;not null" json:"role"`
	Content   string    `gorm:"type:text;not null" json:"content"`
	CreatedAt time.Time `gorm:"not null;autoCreateTime;index:idx_agent_chat_messages_session_created" json:"created_at"`
}

func (AgentChatMessage) TableName() string { return "agent_chat_messages" }

type AgentChatTurn struct {
	ID                 uint            `gorm:"primaryKey;autoIncrement" json:"-"`
	TurnID             string          `gorm:"size:64;not null;uniqueIndex" json:"turn_id"`
	SessionID          uint            `gorm:"not null;index" json:"session_id"`
	UserID             int             `gorm:"not null;index" json:"-"`
	Status             string          `gorm:"size:20;not null;index" json:"status"`
	EventsJSON         json.RawMessage `gorm:"column:events;type:json" json:"events"`
	AssistantMessageID *uint           `gorm:"uniqueIndex" json:"-"`
	ErrorMessage       string          `gorm:"type:text;not null" json:"error_message,omitempty"`
	CreatedAt          time.Time       `gorm:"not null;autoCreateTime" json:"created_at"`
	UpdatedAt          time.Time       `gorm:"not null;autoUpdateTime" json:"updated_at"`
}

func (AgentChatTurn) TableName() string { return "agent_chat_turns" }

type AgentChatTurnResponse struct {
	TurnID           string            `json:"turn_id"`
	SessionID        uint              `json:"session_id"`
	Status           string            `json:"status"`
	Events           json.RawMessage   `json:"events"`
	AssistantMessage *AgentChatMessage `json:"assistant_message"`
	ErrorMessage     string            `json:"error_message"`
	CreatedAt        time.Time         `json:"created_at"`
	UpdatedAt        time.Time         `json:"updated_at"`
}
