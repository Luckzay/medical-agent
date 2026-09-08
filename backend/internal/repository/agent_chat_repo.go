package repository

import (
	"context"
	"encoding/json"

	"medicalagent/internal/model"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

type AgentChatRepository interface {
	CreateSession(ctx context.Context, session *model.AgentSession) error
	ListSessions(ctx context.Context, userID int) ([]model.AgentSession, error)
	GetSession(ctx context.Context, sessionID uint, userID int) (*model.AgentSession, error)
	ListMessages(ctx context.Context, sessionID uint, limit int) ([]model.AgentChatMessage, error)
	CreateUserMessageAndTurn(ctx context.Context, session *model.AgentSession, message *model.AgentChatMessage, turn *model.AgentChatTurn, autoTitle string) error
	GetTurn(ctx context.Context, turnID string, sessionID uint, userID int) (*model.AgentChatTurn, error)
	UpdateTurn(ctx context.Context, turnID string, sessionID uint, userID int, status string, events json.RawMessage, errorMessage string) error
	SaveAssistantMessageOnce(ctx context.Context, turnID string, sessionID uint, userID int, content string) (*model.AgentChatMessage, error)
}

type AgentChatRepo struct{ db *gorm.DB }

func NewAgentChatRepo() *AgentChatRepo { return &AgentChatRepo{db: DB} }

func (r *AgentChatRepo) CreateSession(ctx context.Context, session *model.AgentSession) error {
	return r.db.WithContext(ctx).Create(session).Error
}

func (r *AgentChatRepo) ListSessions(ctx context.Context, userID int) ([]model.AgentSession, error) {
	var sessions []model.AgentSession
	err := r.db.WithContext(ctx).Where("user_id = ?", userID).Order("updated_at DESC, id DESC").Find(&sessions).Error
	return sessions, err
}

func (r *AgentChatRepo) GetSession(ctx context.Context, sessionID uint, userID int) (*model.AgentSession, error) {
	var session model.AgentSession
	if err := r.db.WithContext(ctx).Where("id = ? AND user_id = ?", sessionID, userID).First(&session).Error; err != nil {
		return nil, err
	}
	return &session, nil
}

func (r *AgentChatRepo) ListMessages(ctx context.Context, sessionID uint, limit int) ([]model.AgentChatMessage, error) {
	var messages []model.AgentChatMessage
	q := r.db.WithContext(ctx).Where("session_id = ?", sessionID).Order("id DESC")
	if limit > 0 {
		q = q.Limit(limit)
	}
	if err := q.Find(&messages).Error; err != nil {
		return nil, err
	}
	for left, right := 0, len(messages)-1; left < right; left, right = left+1, right-1 {
		messages[left], messages[right] = messages[right], messages[left]
	}
	return messages, nil
}

func (r *AgentChatRepo) CreateUserMessageAndTurn(ctx context.Context, session *model.AgentSession, message *model.AgentChatMessage, turn *model.AgentChatTurn, autoTitle string) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var owned model.AgentSession
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("id = ? AND user_id = ?", session.ID, session.UserID).First(&owned).Error; err != nil {
			return err
		}
		if err := tx.Create(message).Error; err != nil {
			return err
		}
		if err := tx.Create(turn).Error; err != nil {
			return err
		}
		updates := map[string]any{"updated_at": gorm.Expr("CURRENT_TIMESTAMP")}
		if owned.Title == "" {
			updates["title"] = autoTitle
		}
		return tx.Model(&model.AgentSession{}).Where("id = ? AND user_id = ?", session.ID, session.UserID).Updates(updates).Error
	})
}

func (r *AgentChatRepo) GetTurn(ctx context.Context, turnID string, sessionID uint, userID int) (*model.AgentChatTurn, error) {
	var turn model.AgentChatTurn
	if err := r.db.WithContext(ctx).Where("turn_id = ? AND session_id = ? AND user_id = ?", turnID, sessionID, userID).First(&turn).Error; err != nil {
		return nil, err
	}
	return &turn, nil
}

func (r *AgentChatRepo) UpdateTurn(ctx context.Context, turnID string, sessionID uint, userID int, status string, events json.RawMessage, errorMessage string) error {
	result := r.db.WithContext(ctx).Model(&model.AgentChatTurn{}).Where("turn_id = ? AND session_id = ? AND user_id = ?", turnID, sessionID, userID).Updates(map[string]any{
		"status": status, "events": events, "error_message": errorMessage,
	})
	if result.Error != nil {
		return result.Error
	}
	return nil
}

func (r *AgentChatRepo) SaveAssistantMessageOnce(ctx context.Context, turnID string, sessionID uint, userID int, content string) (*model.AgentChatMessage, error) {
	var message model.AgentChatMessage
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var turn model.AgentChatTurn
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("turn_id = ? AND session_id = ? AND user_id = ?", turnID, sessionID, userID).First(&turn).Error; err != nil {
			return err
		}
		if turn.AssistantMessageID != nil {
			return tx.First(&message, *turn.AssistantMessageID).Error
		}
		message = model.AgentChatMessage{SessionID: sessionID, TurnID: &turnID, Role: model.AgentChatRoleAssistant, Content: content}
		if err := tx.Create(&message).Error; err != nil {
			return err
		}
		return tx.Model(&turn).Where("assistant_message_id IS NULL").Update("assistant_message_id", message.ID).Error
	})
	return &message, err
}
