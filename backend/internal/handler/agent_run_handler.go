package handler

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type agentRunService interface {
	Create(ctx context.Context, input service.CreateAgentRunInput) (model.AgentRunResponse, error)
	Get(ctx context.Context, runID string, userID int) (model.AgentRunResponse, error)
	Resume(ctx context.Context, runID string, userID int) (model.AgentRunResponse, error)
}

type AgentRunHandler struct {
	svc agentRunService
}

func NewAgentRunHandler(svc agentRunService) *AgentRunHandler {
	return &AgentRunHandler{svc: svc}
}

type createAgentRunRequest struct {
	Herbs        []string `json:"herbs"`
	ResearchGoal string   `json:"research_goal"`
}

func (h *AgentRunHandler) Create(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "用户身份无效"})
		return
	}
	var req createAgentRunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求 JSON 无效"})
		return
	}
	if len(req.Herbs) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "herbs 至少需要一项"})
		return
	}
	for i := range req.Herbs {
		req.Herbs[i] = strings.TrimSpace(req.Herbs[i])
		if req.Herbs[i] == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "herbs 不能包含空项"})
			return
		}
	}
	idempotencyKey := strings.TrimSpace(c.GetHeader("Idempotency-Key"))
	if len(idempotencyKey) > 255 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Idempotency-Key 不能超过 255 个字符"})
		return
	}

	result, err := h.svc.Create(c.Request.Context(), service.CreateAgentRunInput{
		UserID:         userID,
		Herbs:          req.Herbs,
		ResearchGoal:   strings.TrimSpace(req.ResearchGoal),
		IdempotencyKey: idempotencyKey,
	})
	if err != nil {
		if errors.Is(err, service.ErrIdempotencyConflict) {
			c.JSON(http.StatusConflict, gin.H{"error": "Idempotency-Key 已用于不同的请求内容"})
			return
		}
		if errors.Is(err, service.ErrAgentUpstream) {
			c.JSON(http.StatusBadGateway, gin.H{"error": "Agent 服务调用失败"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "创建 Agent Run 失败"})
		return
	}
	c.JSON(http.StatusAccepted, gin.H{"data": result})
}

func (h *AgentRunHandler) Get(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "用户身份无效"})
		return
	}
	runID := strings.TrimSpace(c.Param("run_id"))
	if runID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id 不能为空"})
		return
	}
	result, err := h.svc.Get(c.Request.Context(), runID, userID)
	if errors.Is(err, service.ErrAgentRunNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "Agent Run 不存在"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询 Agent Run 失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": result})
}

func (h *AgentRunHandler) Resume(c *gin.Context) {
	userID, ok := currentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "用户身份无效"})
		return
	}
	runID := strings.TrimSpace(c.Param("run_id"))
	if runID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id 不能为空"})
		return
	}

	result, err := h.svc.Resume(c.Request.Context(), runID, userID)
	switch {
	case errors.Is(err, service.ErrAgentRunNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": "Agent Run 不存在"})
	case errors.Is(err, service.ErrAgentRunConflict):
		c.JSON(http.StatusConflict, gin.H{"error": "仅失败状态的 Agent Run 可以恢复"})
	case errors.Is(err, service.ErrAgentUpstream):
		c.JSON(http.StatusBadGateway, gin.H{"error": "Agent 服务恢复调用失败"})
	case err != nil:
		c.JSON(http.StatusInternalServerError, gin.H{"error": "恢复 Agent Run 失败"})
	default:
		c.JSON(http.StatusOK, gin.H{"data": result})
	}
}

func currentUserID(c *gin.Context) (int, bool) {
	value, exists := c.Get("user_id")
	if !exists {
		return 0, false
	}
	userID, ok := value.(int)
	return userID, ok && userID > 0
}
