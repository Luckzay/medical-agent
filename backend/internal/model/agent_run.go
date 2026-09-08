package model

import (
	"encoding/json"
	"fmt"
	"time"
)

const (
	AgentRunStatusPending         = "pending"
	AgentRunStatusRunning         = "running"
	AgentRunStatusCompleted       = "completed"
	AgentRunStatusFailed          = "failed"
	AgentRunStatusCancelled       = "cancelled"
	AgentRunStatusDispatchUnknown = "dispatch_unknown"
)

type AgentRun struct {
	ID                 uint            `gorm:"primaryKey;autoIncrement" json:"-"`
	RunID              string          `gorm:"size:64;not null;uniqueIndex" json:"-"`
	UserID             int             `gorm:"not null;index;uniqueIndex:idx_agent_runs_user_idempotency,priority:1" json:"-"`
	TraceID            string          `gorm:"size:64;not null;index" json:"-"`
	IdempotencyKey     *string         `gorm:"size:255;uniqueIndex:idx_agent_runs_user_idempotency,priority:2" json:"-"`
	RequestHash        string          `gorm:"size:64;not null" json:"-"`
	HerbsJSON          string          `gorm:"type:json;not null" json:"-"`
	ResearchGoal       string          `gorm:"type:text;not null" json:"-"`
	Status             string          `gorm:"size:20;not null;index" json:"-"`
	ErrorMessage       string          `gorm:"type:text;not null" json:"-"`
	AnalysisResultJSON json.RawMessage `gorm:"column:analysis_result;type:json" json:"-"`
	WorkflowJSON       json.RawMessage `gorm:"column:workflow;type:json" json:"-"`
	CreatedAt          time.Time       `gorm:"not null;autoCreateTime" json:"-"`
	UpdatedAt          time.Time       `gorm:"not null;autoUpdateTime" json:"-"`
}

func (AgentRun) TableName() string { return "agent_runs" }

type AgentRunResponse struct {
	RunID          string          `json:"run_id"`
	UserID         int             `json:"user_id"`
	TraceID        string          `json:"trace_id"`
	Herbs          []string        `json:"herbs"`
	ResearchGoal   string          `json:"research_goal"`
	Status         string          `json:"status"`
	ErrorMessage   string          `json:"error_message,omitempty"`
	AnalysisResult json.RawMessage `json:"analysis_result,omitempty"`
	Workflow       json.RawMessage `json:"workflow,omitempty"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

func EncodeHerbs(herbs []string) (string, error) {
	data, err := json.Marshal(herbs)
	if err != nil {
		return "", fmt.Errorf("encode herbs: %w", err)
	}
	return string(data), nil
}

func DecodeHerbs(value string) ([]string, error) {
	var herbs []string
	if err := json.Unmarshal([]byte(value), &herbs); err != nil {
		return nil, fmt.Errorf("decode herbs: %w", err)
	}
	return herbs, nil
}

func (r *AgentRun) Response() (AgentRunResponse, error) {
	herbs, err := DecodeHerbs(r.HerbsJSON)
	if err != nil {
		return AgentRunResponse{}, err
	}
	return AgentRunResponse{
		RunID:          r.RunID,
		UserID:         r.UserID,
		TraceID:        r.TraceID,
		Herbs:          herbs,
		ResearchGoal:   r.ResearchGoal,
		Status:         r.Status,
		ErrorMessage:   r.ErrorMessage,
		AnalysisResult: r.AnalysisResultJSON,
		Workflow:       r.WorkflowJSON,
		CreatedAt:      r.CreatedAt,
		UpdatedAt:      r.UpdatedAt,
	}, nil
}
