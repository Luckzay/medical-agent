package service

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	agentclient "medicalagent/internal/client/agent"
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type chatRepoMock struct {
	turn      model.AgentChatTurn
	message   model.AgentChatMessage
	saveCount int
}

func (*chatRepoMock) CreateSession(context.Context, *model.AgentSession) error { return nil }
func (*chatRepoMock) ListSessions(context.Context, int) ([]model.AgentSession, error) {
	return nil, nil
}
func (*chatRepoMock) GetSession(context.Context, uint, int) (*model.AgentSession, error) {
	return nil, gorm.ErrRecordNotFound
}
func (m *chatRepoMock) ListMessages(context.Context, uint, int) ([]model.AgentChatMessage, error) {
	if m.message.ID == 0 {
		return nil, nil
	}
	return []model.AgentChatMessage{m.message}, nil
}
func (*chatRepoMock) CreateUserMessageAndTurn(context.Context, *model.AgentSession, *model.AgentChatMessage, *model.AgentChatTurn, string) error {
	return nil
}
func (m *chatRepoMock) GetTurn(_ context.Context, turnID string, sessionID uint, userID int) (*model.AgentChatTurn, error) {
	if turnID != m.turn.TurnID || sessionID != m.turn.SessionID || userID != m.turn.UserID {
		return nil, gorm.ErrRecordNotFound
	}
	copy := m.turn
	return &copy, nil
}
func (m *chatRepoMock) UpdateTurn(_ context.Context, _ string, _ uint, _ int, status string, events json.RawMessage, errorMessage string) error {
	m.turn.Status, m.turn.EventsJSON, m.turn.ErrorMessage = status, events, errorMessage
	return nil
}
func (m *chatRepoMock) SaveAssistantMessageOnce(_ context.Context, turnID string, sessionID uint, userID int, content string) (*model.AgentChatMessage, error) {
	m.saveCount++
	if m.message.ID == 0 {
		m.message = model.AgentChatMessage{ID: 99, SessionID: sessionID, TurnID: &turnID, Role: model.AgentChatRoleAssistant, Content: content}
		m.turn.AssistantMessageID = &m.message.ID
	}
	return &m.message, nil
}

type chatClientMock struct{ getCount int }

func (*chatClientMock) CreateTurn(context.Context, agentclient.CreateTurnRequest) (*agentclient.TurnResponse, error) {
	return nil, nil
}
func (m *chatClientMock) GetTurn(_ context.Context, turnID string) (*agentclient.TurnResponse, error) {
	m.getCount++
	return &agentclient.TurnResponse{TurnID: turnID, SessionID: "10", Status: model.AgentChatStatusDone, Events: json.RawMessage(`[{"type":"llm_end"}]`), AssistantMessage: "回答", UpdatedAt: time.Now()}, nil
}

func TestGetTurnSavesAssistantMessageIdempotently(t *testing.T) {
	repo := &chatRepoMock{turn: model.AgentChatTurn{TurnID: "turn-1", SessionID: 10, UserID: 7, Status: model.AgentChatStatusPending, EventsJSON: json.RawMessage("[]")}}
	client := &chatClientMock{}
	svc := NewAgentChatService(repo, client)
	for i := 0; i < 2; i++ {
		response, err := svc.GetTurn(context.Background(), 10, "turn-1", 7)
		if err != nil {
			t.Fatal(err)
		}
		if response.AssistantMessage == nil || response.AssistantMessage.Content != "回答" {
			t.Fatalf("assistant message missing: %+v", response)
		}
	}
	if repo.saveCount != 1 || client.getCount != 1 {
		t.Fatalf("saveCount=%d getCount=%d, want both 1", repo.saveCount, client.getCount)
	}
}

func TestGetTurnEnforcesUserIsolation(t *testing.T) {
	repo := &chatRepoMock{turn: model.AgentChatTurn{TurnID: "turn-1", SessionID: 10, UserID: 7, Status: model.AgentChatStatusFailed}}
	svc := NewAgentChatService(repo, &chatClientMock{})
	if _, err := svc.GetTurn(context.Background(), 10, "turn-1", 8); err != ErrAgentTurnNotFound {
		t.Fatalf("expected ErrAgentTurnNotFound, got %v", err)
	}
}
