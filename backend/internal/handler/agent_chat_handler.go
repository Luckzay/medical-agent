package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type agentChatService interface {
	CreateSession(context.Context, int, string) (*model.AgentSession, error)
	ListSessions(context.Context, int) ([]model.AgentSession, error)
	GetSession(context.Context, uint, int) (*model.AgentSession, []model.AgentChatMessage, error)
	SendMessage(context.Context, uint, int, string) (*model.AgentChatTurn, error)
	GetTurn(context.Context, uint, string, int) (model.AgentChatTurnResponse, error)
}

type AgentChatHandler struct{ svc agentChatService }

func NewAgentChatHandler(svc agentChatService) *AgentChatHandler { return &AgentChatHandler{svc: svc} }

type createAgentSessionRequest struct {
	Title string `json:"title"`
}

type sendAgentMessageRequest struct {
	Content string `json:"content"`
}

func (h *AgentChatHandler) CreateSession(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "用户身份无效"})
		return
	}
	var req createAgentSessionRequest
	if c.Request.ContentLength != 0 {
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "请求 JSON 无效"})
			return
		}
	}
	session, err := h.svc.CreateSession(c.Request.Context(), userID, req.Title)
	if errors.Is(err, service.ErrInvalidChatMessage) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "title 不能超过 255 个字符"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "创建会话失败"})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"data": session})
}

func (h *AgentChatHandler) ListSessions(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "用户身份无效"})
		return
	}
	sessions, err := h.svc.ListSessions(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询会话失败"})
		return
	}
	if sessions == nil {
		sessions = []model.AgentSession{}
	}
	c.JSON(http.StatusOK, gin.H{"data": sessions})
}

func (h *AgentChatHandler) GetSession(c *gin.Context) {
	userID, sessionID, ok := chatRouteIdentity(c)
	if !ok {
		return
	}
	session, messages, err := h.svc.GetSession(c.Request.Context(), sessionID, userID)
	if errors.Is(err, service.ErrAgentSessionNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "会话不存在"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询会话失败"})
		return
	}
	if messages == nil {
		messages = []model.AgentChatMessage{}
	}
	c.JSON(http.StatusOK, gin.H{"data": gin.H{"session": session, "messages": messages}})
}

func (h *AgentChatHandler) SendMessage(c *gin.Context) {
	userID, sessionID, ok := chatRouteIdentity(c)
	if !ok {
		return
	}
	var req sendAgentMessageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求 JSON 无效"})
		return
	}
	turn, err := h.svc.SendMessage(c.Request.Context(), sessionID, userID, req.Content)
	switch {
	case errors.Is(err, service.ErrInvalidChatMessage):
		c.JSON(http.StatusBadRequest, gin.H{"error": "content 必填且不能超过 8000 个字符"})
	case errors.Is(err, service.ErrAgentSessionNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "会话不存在"})
	case errors.Is(err, service.ErrAgentUpstream):
		c.JSON(http.StatusBadGateway, gin.H{"error": "Agent 服务调用失败"})
	case err != nil:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "发送消息失败"})
	default:
		c.JSON(http.StatusAccepted, gin.H{"data": gin.H{"turn_id": turn.TurnID, "status": turn.Status}})
	}
}

func (h *AgentChatHandler) GetTurn(c *gin.Context) {
	userID, sessionID, ok := chatRouteIdentity(c)
	if !ok {
		return
	}
	turnID := strings.TrimSpace(c.Param("turn_id"))
	if turnID == "" || len(turnID) > 64 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "turn_id 无效"})
		return
	}
	turn, err := h.svc.GetTurn(c.Request.Context(), sessionID, turnID, userID)
	if errors.Is(err, service.ErrAgentTurnNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "Turn 不存在"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询 Turn 失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": turn})
}

func chatRouteIdentity(c *gin.Context) (int, uint, bool) {
	userID, ok := currentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "用户身份无效"})
		return 0, 0, false
	}
	parsed, err := strconv.ParseUint(c.Param("id"), 10, 64)
	if err != nil || parsed == 0 || uint64(uint(parsed)) != parsed {
		c.JSON(http.StatusBadRequest, gin.H{"error": "会话 id 无效"})
		return 0, 0, false
	}
	return userID, uint(parsed), true
}

var (
	agentTurnPollInterval = 200 * time.Millisecond
	agentTurnHeartbeat    = 15 * time.Second
)

func (h *AgentChatHandler) StreamTurn(c *gin.Context) {
	userID, sessionID, ok := chatRouteIdentity(c)
	if !ok {
		return
	}
	turnID := strings.TrimSpace(c.Param("turn_id"))
	if turnID == "" || len(turnID) > 64 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "turn_id 无效"})
		return
	}

	// Fetch before committing SSE headers so authorization/not-found errors retain
	// their normal HTTP status. GetTurn enforces the user/session/turn tuple.
	turn, err := h.svc.GetTurn(c.Request.Context(), sessionID, turnID, userID)
	if errors.Is(err, service.ErrAgentTurnNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "Turn 不存在"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询 Turn 失败"})
		return
	}

	c.Header("Content-Type", "text/event-stream; charset=utf-8")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)
	c.Writer.Flush()

	lastSequence := int64(0)
	emitTurn := func(current model.AgentChatTurnResponse) error {
		var events []json.RawMessage
		if len(current.Events) != 0 {
			if err := json.Unmarshal(current.Events, &events); err != nil {
				return fmt.Errorf("decode turn events: %w", err)
			}
		}
		for _, raw := range events {
			var envelope struct {
				Sequence int64 `json:"sequence"`
			}
			if err := json.Unmarshal(raw, &envelope); err != nil || envelope.Sequence <= lastSequence {
				continue
			}
			if err := writeSSE(c, "execution", raw); err != nil {
				return err
			}
			lastSequence = envelope.Sequence
		}
		if current.Status == model.AgentChatStatusDone || current.Status == model.AgentChatStatusFailed {
			return writeSSE(c, "turn", current)
		}
		return nil
	}
	if err := emitTurn(turn); err != nil || turn.Status == model.AgentChatStatusDone || turn.Status == model.AgentChatStatusFailed {
		return
	}

	poll := time.NewTicker(agentTurnPollInterval)
	heartbeat := time.NewTicker(agentTurnHeartbeat)
	defer poll.Stop()
	defer heartbeat.Stop()
	for {
		select {
		case <-c.Request.Context().Done():
			return
		case <-heartbeat.C:
			if _, err := c.Writer.Write([]byte(": heartbeat\n\n")); err != nil {
				return
			}
			c.Writer.Flush()
		case <-poll.C:
			current, err := h.svc.GetTurn(c.Request.Context(), sessionID, turnID, userID)
			if err != nil {
				return
			}
			if err := emitTurn(current); err != nil {
				return
			}
			if current.Status == model.AgentChatStatusDone || current.Status == model.AgentChatStatusFailed {
				return
			}
		}
	}
}

func writeSSE(c *gin.Context, event string, data any) error {
	payload, err := json.Marshal(data)
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintf(c.Writer, "event: %s\ndata: %s\n\n", event, payload); err != nil {
		return err
	}
	c.Writer.Flush()
	return nil
}
