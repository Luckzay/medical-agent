package service

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"medicalagent/internal/model"
	"medicalagent/internal/util"
)

func TestChatMessagesStreamForwardsContentAndToolCallDeltas(t *testing.T) {
	masterKey := []byte("12345678901234567890123456789012")
	encrypted, err := util.Encrypt("never-log-this-key", masterKey)
	if err != nil {
		t.Fatal(err)
	}
	longArguments := strings.Repeat("x", 70<<10)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Stream bool `json:"stream"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !body.Stream {
			t.Fatalf("stream was not enabled: %+v, %v", body, err)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		// Deliberately use CRLF and a frame larger than bufio.Scanner's default limit.
		_, _ = w.Write([]byte("data: {\"model\":\"actual-model\",\"choices\":[{\"delta\":{\"content\":\"你好\",\"tool_calls\":[{\"index\":0,\"id\":\"call-1\",\"function\":{\"name\":\"search\",\"arguments\":\"" + longArguments + "\"}}]}}]}\r\n\r\n"))
		_, _ = w.Write([]byte("data: [DONE]\r\n\r\n"))
	}))
	defer upstream.Close()

	svc := NewLLMConfigService(&mockLLMConfigRepo{cfg: &model.LLMConfig{Provider: "openai-compatible", BaseURL: upstream.URL, ModelName: "configured-model", APIKeyEncrypted: encrypted, Enabled: true}}, string(masterKey), "token").(*llmConfigService)
	var events []LLMStreamEvent
	err = svc.ChatMessagesStream(context.Background(), LLMChatRequest{Messages: []LLMChatMessage{{Role: "user", Content: "test"}}}, func(event LLMStreamEvent) error {
		events = append(events, event)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(events) != 3 || events[0].Event != "delta" || events[1].Event != "tool_call_delta" || events[2].Event != "done" {
		t.Fatalf("unexpected events: %#v", events)
	}
	tool := events[1].Data.(LLMToolCallDeltaEvent)
	if tool.ID != "call-1" || tool.Name != "search" || tool.Arguments != longArguments {
		t.Fatalf("unexpected tool delta: id=%q name=%q argument length=%d", tool.ID, tool.Name, len(tool.Arguments))
	}
	if done := events[2].Data.(LLMDoneEvent); done.Model != "actual-model" || done.Provider != "openai-compatible" {
		t.Fatalf("unexpected done event: %+v", done)
	}
}

func TestChatMessagesStreamReturnsUpstreamNon2xx(t *testing.T) {
	masterKey := []byte("12345678901234567890123456789012")
	encrypted, _ := util.Encrypt("secret", masterKey)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "sensitive upstream body", http.StatusTooManyRequests)
	}))
	defer upstream.Close()
	svc := NewLLMConfigService(&mockLLMConfigRepo{cfg: &model.LLMConfig{Provider: "test", BaseURL: upstream.URL, ModelName: "model", APIKeyEncrypted: encrypted, Enabled: true}}, string(masterKey), "token").(*llmConfigService)
	err := svc.ChatMessagesStream(context.Background(), LLMChatRequest{Messages: []LLMChatMessage{{Role: "user", Content: "test"}}}, func(LLMStreamEvent) error { return nil })
	if err == nil || !strings.Contains(err.Error(), "status 429") || strings.Contains(err.Error(), "sensitive upstream body") {
		t.Fatalf("unexpected error: %v", err)
	}
}
