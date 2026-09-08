package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"unicode/utf8"

	agentclient "medicalagent/internal/client/agent"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"

	"gorm.io/gorm"
)

const MaxChatMessageRunes = 8000

var (
	ErrAgentSessionNotFound = errors.New("agent session not found")
	ErrAgentTurnNotFound    = errors.New("agent chat turn not found")
	ErrInvalidChatMessage   = errors.New("invalid chat message")
)

type AgentChatService struct {
	repo   repository.AgentChatRepository
	client agentclient.ChatClient
}

func NewAgentChatService(repo repository.AgentChatRepository, client agentclient.ChatClient) *AgentChatService {
	return &AgentChatService{repo: repo, client: client}
}

func (s *AgentChatService) CreateSession(ctx context.Context, userID int, title string) (*model.AgentSession, error) {
	title = strings.TrimSpace(title)
	if len([]rune(title)) > 255 {
		return nil, ErrInvalidChatMessage
	}
	session := &model.AgentSession{UserID: userID, Title: title}
	if err := s.repo.CreateSession(ctx, session); err != nil {
		return nil, fmt.Errorf("create agent session: %w", err)
	}
	return session, nil
}

func (s *AgentChatService) ListSessions(ctx context.Context, userID int) ([]model.AgentSession, error) {
	return s.repo.ListSessions(ctx, userID)
}

func (s *AgentChatService) GetSession(ctx context.Context, sessionID uint, userID int) (*model.AgentSession, []model.AgentChatMessage, error) {
	session, err := s.repo.GetSession(ctx, sessionID, userID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil, ErrAgentSessionNotFound
	}
	if err != nil {
		return nil, nil, fmt.Errorf("get agent session: %w", err)
	}
	messages, err := s.repo.ListMessages(ctx, sessionID, 0)
	if err != nil {
		return nil, nil, fmt.Errorf("list agent messages: %w", err)
	}
	return session, messages, nil
}

func (s *AgentChatService) SendMessage(ctx context.Context, sessionID uint, userID int, content string) (*model.AgentChatTurn, error) {
	content = strings.TrimSpace(content)
	if content == "" || utf8.RuneCountInString(content) > MaxChatMessageRunes {
		return nil, ErrInvalidChatMessage
	}
	session, err := s.repo.GetSession(ctx, sessionID, userID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrAgentSessionNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("get agent session for message: %w", err)
	}
	turnID, err := secureID("turn")
	if err != nil {
		return nil, err
	}
	message := &model.AgentChatMessage{SessionID: sessionID, TurnID: &turnID, Role: model.AgentChatRoleUser, Content: content}
	turn := &model.AgentChatTurn{TurnID: turnID, SessionID: sessionID, UserID: userID, Status: model.AgentChatStatusPending, EventsJSON: json.RawMessage("[]")}
	if err := s.repo.CreateUserMessageAndTurn(ctx, session, message, turn, truncateRunes(content, 30)); err != nil {
		return nil, fmt.Errorf("persist user message: %w", err)
	}
	history, err := s.repo.ListMessages(ctx, sessionID, 21)
	if err != nil {
		s.markTurnFailed(ctx, turn, "failed to load chat history")
		return nil, fmt.Errorf("load chat history: %w", err)
	}
	messages := make([]agentclient.ChatMessage, 0, 20)
	for _, item := range history {
		if item.ID == message.ID {
			continue
		}
		messages = append(messages, agentclient.ChatMessage{Role: item.Role, Content: item.Content})
		if len(messages) == 20 {
			break
		}
	}
	remote, err := s.client.CreateTurn(ctx, agentclient.CreateTurnRequest{
		TurnID: turnID, SessionID: strconv.FormatUint(uint64(sessionID), 10), UserID: strconv.Itoa(userID), Message: content, History: messages,
	})
	if err != nil {
		s.markTurnFailed(ctx, turn, "agent service dispatch failed")
		return nil, fmt.Errorf("%w: create chat turn: %v", ErrAgentUpstream, err)
	}
	if remote.TurnID != "" && remote.TurnID != turnID {
		s.markTurnFailed(ctx, turn, "agent service returned mismatched turn")
		return nil, fmt.Errorf("%w: mismatched turn id", ErrAgentUpstream)
	}
	if remote.SessionID != "" && remote.SessionID != strconv.FormatUint(uint64(sessionID), 10) {
		s.markTurnFailed(ctx, turn, "agent service returned mismatched session")
		return nil, fmt.Errorf("%w: mismatched session id", ErrAgentUpstream)
	}
	status := normalizeChatStatus(remote.Status)
	if err := s.repo.UpdateTurn(ctx, turnID, sessionID, userID, status, remote.Events, remote.ErrorMessage); err != nil {
		return nil, fmt.Errorf("update dispatched chat turn: %w", err)
	}
	turn.Status, turn.EventsJSON, turn.ErrorMessage = status, remote.Events, remote.ErrorMessage
	return turn, nil
}

func (s *AgentChatService) GetTurn(ctx context.Context, sessionID uint, turnID string, userID int) (model.AgentChatTurnResponse, error) {
	turn, err := s.repo.GetTurn(ctx, turnID, sessionID, userID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return model.AgentChatTurnResponse{}, ErrAgentTurnNotFound
	}
	if err != nil {
		return model.AgentChatTurnResponse{}, fmt.Errorf("get chat turn: %w", err)
	}
	if turn.Status == model.AgentChatStatusPending || turn.Status == model.AgentChatStatusRunning || (turn.Status == model.AgentChatStatusDone && turn.AssistantMessageID == nil) {
		remote, pollErr := s.client.GetTurn(ctx, turnID)
		if pollErr == nil && remote != nil && (remote.TurnID == "" || remote.TurnID == turnID) && (remote.SessionID == "" || remote.SessionID == strconv.FormatUint(uint64(sessionID), 10)) {
			status := normalizeChatStatus(remote.Status)
			if err := s.repo.UpdateTurn(ctx, turnID, sessionID, userID, status, remote.Events, remote.ErrorMessage); err == nil {
				turn.Status, turn.EventsJSON, turn.ErrorMessage = status, remote.Events, remote.ErrorMessage
				turn.UpdatedAt = remote.UpdatedAt
			}
			if status == model.AgentChatStatusDone && strings.TrimSpace(remote.AssistantMessage) != "" {
				message, saveErr := s.repo.SaveAssistantMessageOnce(ctx, turnID, sessionID, userID, remote.AssistantMessage)
				if saveErr != nil {
					return model.AgentChatTurnResponse{}, fmt.Errorf("save assistant message: %w", saveErr)
				}
				turn.AssistantMessageID = &message.ID
			}
		}
	}
	response := turnResponse(turn, nil)
	if turn.AssistantMessageID != nil {
		messages, listErr := s.repo.ListMessages(ctx, sessionID, 0)
		if listErr != nil {
			return model.AgentChatTurnResponse{}, fmt.Errorf("load assistant message: %w", listErr)
		}
		for i := range messages {
			if messages[i].ID == *turn.AssistantMessageID {
				response.AssistantMessage = &messages[i]
				break
			}
		}
	}
	return response, nil
}

func (s *AgentChatService) markTurnFailed(ctx context.Context, turn *model.AgentChatTurn, message string) {
	_ = s.repo.UpdateTurn(ctx, turn.TurnID, turn.SessionID, turn.UserID, model.AgentChatStatusFailed, turn.EventsJSON, message)
}

func normalizeChatStatus(status string) string {
	switch status {
	case model.AgentChatStatusPending, model.AgentChatStatusRunning, model.AgentChatStatusDone, model.AgentChatStatusFailed:
		return status
	default:
		return model.AgentChatStatusPending
	}
}

func turnResponse(turn *model.AgentChatTurn, assistant *model.AgentChatMessage) model.AgentChatTurnResponse {
	events := turn.EventsJSON
	if len(events) == 0 {
		events = json.RawMessage("[]")
	}
	return model.AgentChatTurnResponse{TurnID: turn.TurnID, SessionID: turn.SessionID, Status: turn.Status, Events: events, AssistantMessage: assistant, ErrorMessage: turn.ErrorMessage, CreatedAt: turn.CreatedAt, UpdatedAt: turn.UpdatedAt}
}

func truncateRunes(value string, max int) string {
	runes := []rune(value)
	if len(runes) <= max {
		return value
	}
	return string(runes[:max])
}
