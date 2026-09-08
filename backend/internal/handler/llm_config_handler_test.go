package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"medicalagent/internal/model"

	"github.com/gin-gonic/gin"
)

type mockLLMConfigService struct{}

func (m *mockLLMConfigService) GetConfig(ctx context.Context) (model.LLMConfigResponse, error) {
	return model.LLMConfigResponse{}, nil
}
func (m *mockLLMConfigService) UpdateConfig(ctx context.Context, input model.LLMConfig, plainKey string) error {
	return nil
}
func (m *mockLLMConfigService) Chat(ctx context.Context, system, user string) (map[string]any, error) {
	return map[string]any{"content": "hi"}, nil
}
func (m *mockLLMConfigService) VerifyInternalToken(token string) bool {
	return token == "secret"
}

// Minimal interfaces for mocking (would need to match the actual service interface)
// Using 'any' here for simplicity in the test setup if needed, but it's better to use the real type.

func TestInternalChatAuth(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockSvc := &mockLLMConfigService{}
	// Note: In real code, service interface should be used.
	// The handler uses service.LLMConfigService interface.

	h := NewLLMConfigHandler(mockSvc)

	r := gin.New()
	r.POST("/internal/v1/llm/chat", h.InternalChat)

	t.Run("Unauthorized", func(t *testing.T) {
		w := httptest.NewRecorder()
		req, _ := http.NewRequest("POST", "/internal/v1/llm/chat", nil)
		r.ServeHTTP(w, req)
		if w.Code != http.StatusUnauthorized {
			t.Errorf("Expected 401, got %d", w.Code)
		}
	})

	t.Run("Authorized", func(t *testing.T) {
		w := httptest.NewRecorder()
		body := map[string]string{
			"system_prompt": "sys",
			"user_prompt":   "user",
		}
		jsonBody, _ := json.Marshal(body)
		req, _ := http.NewRequest("POST", "/internal/v1/llm/chat", bytes.NewBuffer(jsonBody))
		req.Header.Set("X-Agent-Token", "secret")
		req.Header.Set("Content-Type", "application/json")
		r.ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Errorf("Expected 200, got %d. Body: %s", w.Code, w.Body.String())
		}
	})
}
