package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type LLMConfigHandler struct{ svc service.LLMConfigService }

func NewLLMConfigHandler(svc service.LLMConfigService) *LLMConfigHandler {
	return &LLMConfigHandler{svc: svc}
}

func (h *LLMConfigHandler) Get(c *gin.Context) {
	resp, err := h.svc.GetConfig(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "LLM config not found"})
		return
	}
	c.JSON(http.StatusOK, resp)
}

type updateLLMConfigRequest struct {
	Provider  string `json:"provider" binding:"required"`
	BaseURL   string `json:"base_url" binding:"required"`
	APIKey    string `json:"api_key"`
	ModelName string `json:"model_name" binding:"required"`
	Enabled   bool   `json:"enabled"`
}

func (h *LLMConfigHandler) Update(c *gin.Context) {
	var req updateLLMConfigRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	userID, _ := c.Get("user_id")
	uid, _ := userID.(int)
	cfg := model.LLMConfig{Provider: req.Provider, BaseURL: req.BaseURL, ModelName: req.ModelName, Enabled: req.Enabled, UpdatedBy: uid}
	if err := h.svc.UpdateConfig(c.Request.Context(), cfg, req.APIKey); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "LLM config updated successfully"})
}

type chatRequest struct {
	SystemPrompt string                   `json:"system_prompt"`
	UserPrompt   string                   `json:"user_prompt"`
	Messages     []service.LLMChatMessage `json:"messages"`
	Tools        []json.RawMessage        `json:"tools"`
	ToolChoice   string                   `json:"tool_choice"`
}

func (h *LLMConfigHandler) InternalChat(c *gin.Context) {
	if !h.svc.VerifyInternalToken(c.GetHeader("X-Agent-Token")) {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized internal access"})
		return
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, service.MaxLLMRequestBodySize)
	var req chatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chat request"})
		return
	}
	if len(req.Messages) == 0 {
		if strings.TrimSpace(req.SystemPrompt) == "" || strings.TrimSpace(req.UserPrompt) == "" || len(req.Tools) > 0 || req.ToolChoice != "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "system_prompt and user_prompt are required"})
			return
		}
		result, err := h.svc.Chat(c.Request.Context(), req.SystemPrompt, req.UserPrompt)
		h.writeChatResult(c, result, err)
		return
	}
	if req.SystemPrompt != "" || req.UserPrompt != "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "legacy prompts cannot be mixed with messages"})
		return
	}
	advanced, ok := h.svc.(interface {
		ChatMessages(context.Context, service.LLMChatRequest) (service.LLMChatResponse, error)
	})
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "structured chat is unavailable"})
		return
	}
	result, err := advanced.ChatMessages(c.Request.Context(), service.LLMChatRequest{Messages: req.Messages, Tools: req.Tools, ToolChoice: req.ToolChoice})
	if errors.Is(err, service.ErrInvalidLLMRequest) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chat request"})
		return
	}
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "LLM request failed"})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (h *LLMConfigHandler) writeChatResult(c *gin.Context, result map[string]any, err error) {
	if errors.Is(err, service.ErrInvalidLLMRequest) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chat request"})
		return
	}
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "LLM request failed"})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (h *LLMConfigHandler) InternalChatStream(c *gin.Context) {
	if !h.svc.VerifyInternalToken(c.GetHeader("X-Agent-Token")) {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized internal access"})
		return
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, service.MaxLLMRequestBodySize)
	var req chatRequest
	if err := c.ShouldBindJSON(&req); err != nil || len(req.Messages) == 0 || req.SystemPrompt != "" || req.UserPrompt != "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chat request"})
		return
	}
	streamer, ok := h.svc.(interface {
		ChatMessagesStream(context.Context, service.LLMChatRequest, func(service.LLMStreamEvent) error) error
	})
	if !ok {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "streaming chat is unavailable"})
		return
	}
	started := false
	emit := func(event service.LLMStreamEvent) error {
		if !started {
			c.Header("Content-Type", "text/event-stream; charset=utf-8")
			c.Header("Cache-Control", "no-cache")
			c.Header("Connection", "keep-alive")
			c.Header("X-Accel-Buffering", "no")
			c.Status(http.StatusOK)
			started = true
		}
		payload, err := json.Marshal(event.Data)
		if err != nil {
			return err
		}
		if _, err := fmt.Fprintf(c.Writer, "event: %s\ndata: %s\n\n", event.Event, payload); err != nil {
			return err
		}
		c.Writer.Flush()
		return c.Request.Context().Err()
	}
	err := streamer.ChatMessagesStream(c.Request.Context(), service.LLMChatRequest{Messages: req.Messages, Tools: req.Tools, ToolChoice: req.ToolChoice}, emit)
	if err == nil || errors.Is(err, context.Canceled) {
		return
	}
	if !started {
		if errors.Is(err, service.ErrInvalidLLMRequest) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chat request"})
			return
		}
	}
	_ = emit(service.LLMStreamEvent{Event: "error", Data: service.LLMErrorEvent{Error: "LLM stream failed"}})
}
