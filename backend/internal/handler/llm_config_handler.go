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

// Get godoc
// @Summary      获取 LLM 配置
// @Description  管理员查看当前的 LLM 提供商、基础 URL 和模型名称（API Key 会被脱敏）
// @Tags         admin
// @Produce      json
// @Success      200  {object}  model.LLMConfig
// @Failure      404  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/admin/llm-config [get]
func (h *LLMConfigHandler) Get(c *gin.Context) {
	resp, err := h.svc.GetConfig(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "LLM config not found"})
		return
	}
	c.JSON(http.StatusOK, resp)
}

type updateLLMConfigRequest struct {
	Provider  string `json:"provider" binding:"required" example:"openai"`
	BaseURL   string `json:"base_url" binding:"required" example:"https://api.openai.com/v1"`
	APIKey    string `json:"api_key" example:"sk-..."`
	ModelName string `json:"model_name" binding:"required" example:"gpt-4"`
	Enabled   bool   `json:"enabled" example:"true"`
}

// Update godoc
// @Summary      更新 LLM 配置
// @Description  管理员更新 LLM 配置信息
// @Tags         admin
// @Accept       json
// @Produce      json
// @Param        request  body      updateLLMConfigRequest  true  "配置信息"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/admin/llm-config [put]
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
	SystemPrompt string                   `json:"system_prompt" example:"你是一个中医专家"`
	UserPrompt   string                   `json:"user_prompt" example:"请解释什么是辨证论治"`
	Messages     []service.LLMChatMessage `json:"messages"`
	Tools        []json.RawMessage        `json:"tools"`
	ToolChoice   string                   `json:"tool_choice"`
}

// InternalChat godoc
// @Summary      内部 LLM 对话接口
// @Description  供 Agent 服务内部调用的 LLM 对话接口
// @Tags         internal
// @Accept       json
// @Produce      json
// @Param        X-Agent-Token  header  string  true  "内部认证令牌"
// @Param        request  body      chatRequest  true  "对话请求"
// @Success      200  {object}  service.LLMChatResponse
// @Failure      400  {object}  object{error=string}
// @Failure      401  {object}  object{error=string}
// @Failure      502  {object}  object{error=string}
// @Security     AgentTokenAuth
// @Router       /internal/v1/llm/chat [post]
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

// InternalChatStream godoc
// @Summary      内部 LLM 流式对话接口
// @Description  供 Agent 服务内部调用的 LLM 流式对话接口 (SSE)。
// @Description  事件帧格式为标准的 SSE 格式，包含 event 和 data 字段。
// @Description  常见事件类型:
// @Description  1. "message": 对话内容增量帧。
// @Description  2. "error": 发生错误时的通知帧。
// @Description  3. "done": 对话正常结束的标记。
// @Tags         internal
// @Accept       json
// @Produce      text/event-stream
// @Param        X-Agent-Token  header  string  true  "内部认证令牌"
// @Param        request  body      chatRequest  true  "对话请求"
// @Success      200  {string}  string  "SSE stream"
// @Failure      400  {object}  object{error=string}
// @Failure      401  {object}  object{error=string}
// @Security     AgentTokenAuth
// @Router       /internal/v1/llm/chat/stream [post]
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
