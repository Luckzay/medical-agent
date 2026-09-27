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
	Title string `json:"title" example:"关于麻黄的药理咨询"`
}

type sendAgentMessageRequest struct {
	Content string `json:"content" example:"请分析麻黄在宣肺平喘方面的科学原理"`
}

// CreateSession godoc
// @Summary      创建对话会话
// @Description  为用户创建一个新的 Agent 对话会话
// @Tags         agent-chat
// @Accept       json
// @Produce      json
// @Param        request  body      createAgentSessionRequest  false  "会话信息"
// @Success      201  {object}  object{data=model.AgentSession}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/agent/sessions [post]
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

// ListSessions godoc
// @Summary      获取对话会话列表
// @Description  获取当前用户的所有 Agent 对话会话
// @Tags         agent-chat
// @Produce      json
// @Success      200  {object}  object{data=[]model.AgentSession}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/agent/sessions [get]
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

// GetSession godoc
// @Summary      获取会话详情
// @Description  获取指定会话的详情及所有历史消息
// @Tags         agent-chat
// @Produce      json
// @Param        id   path      int  true  "会话 ID"
// @Success      200  {object}  object{data=object{session=model.AgentSession,messages=[]model.AgentChatMessage}}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/agent/sessions/{id} [get]
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

// SendMessage godoc
// @Summary      发送对话消息
// @Description  在指定会话中发送消息，返回生成的 Turn ID
// @Tags         agent-chat
// @Accept       json
// @Produce      json
// @Param        id       path      int                      true  "会话 ID"
// @Param        request  body      sendAgentMessageRequest  true  "消息内容"
// @Success      202  {object}  object{data=object{turn_id=string,status=string}}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/agent/sessions/{id}/messages [post]
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

// GetTurn godoc
// @Summary      获取对话轮次结果
// @Description  获取指定对话轮次（Turn）的当前状态 and 分析结果
// @Tags         agent-chat
// @Produce      json
// @Param        id       path      int     true  "会话 ID"
// @Param        turn_id  path      string  true  "轮次 ID"
// @Success      200  {object}  object{data=model.AgentChatTurnResponse}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/agent/sessions/{id}/turns/{turn_id} [get]
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

// StreamTurn godoc
// @Summary      流式获取轮次进度 (SSE)
// @Description  通过 SSE 流式获取轮次的执行进度、事件以及最终结果。
// @Description  事件帧格式为 Data: {sequence: int64, ...}。
// @Description  事件类型包括:
// @Description  1. "execution": 包含中间执行步骤的事件帧。
// @Description  2. "turn": 包含最终状态 (done/failed) 和完整结果的结束帧。
// @Description  当收到 status 为 "done" 或 "failed" 的 "turn" 事件，或连接断开时，流式传输结束。
// @Tags         agent-chat
// @Produce      text/event-stream
// @Param        id       path      int     true  "会话 ID"
// @Param        turn_id  path      string  true  "轮次 ID"
// @Success      200  {string}  string  "SSE stream"
// @Security     BearerAuth
// @Router       /api/agent/sessions/{id}/turns/{turn_id}/stream [get]
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
