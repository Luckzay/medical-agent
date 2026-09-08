package service

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"medicalagent/internal/model"
	"medicalagent/internal/util"
)

func TestChatMessagesProxiesToolsAndReturnsToolCalls(t *testing.T) {
	masterKey := []byte("12345678901234567890123456789012")
	encrypted, err := util.Encrypt("secret-api-key", masterKey)
	if err != nil {
		t.Fatal(err)
	}
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer secret-api-key" {
			t.Fatal("missing upstream authorization")
		}
		var body map[string]json.RawMessage
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if len(body["tools"]) == 0 || string(body["tool_choice"]) != `"auto"` {
			t.Fatalf("tools were not proxied: %s", body)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"model":"upstream-model","choices":[{"message":{"content":"","tool_calls":[{"id":"call_1","type":"function","function":{"name":"search","arguments":"{}"}}]}}]}`))
	}))
	defer upstream.Close()

	repo := &mockLLMConfigRepo{cfg: &model.LLMConfig{Provider: "openai-compatible", BaseURL: upstream.URL, ModelName: "configured-model", APIKeyEncrypted: encrypted, Enabled: true}}
	svc := NewLLMConfigService(repo, string(masterKey), "token")
	advanced := svc.(interface {
		ChatMessages(context.Context, LLMChatRequest) (LLMChatResponse, error)
	})
	response, err := advanced.ChatMessages(context.Background(), LLMChatRequest{
		Messages:   []LLMChatMessage{{Role: "user", Content: "查药材"}},
		Tools:      []json.RawMessage{json.RawMessage(`{"type":"function","function":{"name":"search"}}`)},
		ToolChoice: "auto",
	})
	if err != nil {
		t.Fatal(err)
	}
	if response.Model != "upstream-model" || len(response.ToolCalls) != 1 {
		t.Fatalf("unexpected response: %+v", response)
	}
}

func TestChatMessagesRejectsOversizedAndInvalidRequests(t *testing.T) {
	svc := NewLLMConfigService(&mockLLMConfigRepo{}, "12345678901234567890123456789012", "token")
	advanced := svc.(interface {
		ChatMessages(context.Context, LLMChatRequest) (LLMChatResponse, error)
	})
	_, err := advanced.ChatMessages(context.Background(), LLMChatRequest{Messages: make([]LLMChatMessage, MaxLLMMessages+1)})
	if err != ErrInvalidLLMRequest {
		t.Fatalf("expected ErrInvalidLLMRequest, got %v", err)
	}
}
