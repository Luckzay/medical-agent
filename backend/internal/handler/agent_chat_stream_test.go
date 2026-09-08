package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type streamChatServiceMock struct {
	calls       atomic.Int32
	cancelSeen  chan struct{}
	expectedUID int
}

func (*streamChatServiceMock) CreateSession(context.Context, int, string) (*model.AgentSession, error) {
	return nil, nil
}
func (*streamChatServiceMock) ListSessions(context.Context, int) ([]model.AgentSession, error) {
	return nil, nil
}
func (*streamChatServiceMock) GetSession(context.Context, uint, int) (*model.AgentSession, []model.AgentChatMessage, error) {
	return nil, nil, nil
}
func (*streamChatServiceMock) SendMessage(context.Context, uint, int, string) (*model.AgentChatTurn, error) {
	return nil, nil
}
func (m *streamChatServiceMock) GetTurn(ctx context.Context, sessionID uint, turnID string, userID int) (model.AgentChatTurnResponse, error) {
	if userID != m.expectedUID || sessionID != 10 || turnID != "turn-1" {
		return model.AgentChatTurnResponse{}, service.ErrAgentTurnNotFound
	}
	if m.cancelSeen != nil {
		select {
		case <-ctx.Done():
			select {
			case <-m.cancelSeen:
			default:
				close(m.cancelSeen)
			}
			return model.AgentChatTurnResponse{}, ctx.Err()
		default:
		}
	}
	call := m.calls.Add(1)
	events := `[ {"sequence":1,"type":"start"} ]`
	status := model.AgentChatStatusPending
	if call >= 2 {
		events = `[{"sequence":1,"type":"start"},{"sequence":2,"type":"delta","delta":"好"}]`
		status = model.AgentChatStatusRunning
	}
	if call >= 3 && m.cancelSeen == nil {
		status = model.AgentChatStatusDone
	}
	return model.AgentChatTurnResponse{TurnID: turnID, SessionID: sessionID, Status: status, Events: json.RawMessage(events)}, nil
}

func streamTestRouter(mock agentChatService, withUser bool) *gin.Engine {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.GET("/api/agent/sessions/:id/turns/:turn_id/stream", func(c *gin.Context) {
		if withUser {
			c.Set("user_id", 7)
		}
		c.Next()
	}, NewAgentChatHandler(mock).StreamTurn)
	return router
}

func TestAgentTurnStreamIncrementalAndTerminal(t *testing.T) {
	oldPoll := agentTurnPollInterval
	agentTurnPollInterval = time.Millisecond
	defer func() { agentTurnPollInterval = oldPoll }()
	mock := &streamChatServiceMock{expectedUID: 7}
	response := httptest.NewRecorder()
	streamTestRouter(mock, true).ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/api/agent/sessions/10/turns/turn-1/stream", nil))
	if response.Code != http.StatusOK || response.Header().Get("X-Accel-Buffering") != "no" || !strings.HasPrefix(response.Header().Get("Content-Type"), "text/event-stream") {
		t.Fatalf("status=%d headers=%v", response.Code, response.Header())
	}
	body := response.Body.String()
	if strings.Count(body, "event: execution\n") != 2 {
		t.Fatalf("events were not incremental: %s", body)
	}
	terminalAt := strings.Index(body, "event: turn\n")
	if terminalAt < 0 || strings.Count(body[:terminalAt], `"sequence":1`) != 1 || strings.Count(body[:terminalAt], `"sequence":2`) != 1 {
		t.Fatalf("execution events were duplicated: %s", body)
	}
	if !strings.Contains(body, `"status":"completed"`) {
		t.Fatalf("terminal turn missing: %s", body)
	}
}

func TestAgentTurnStreamRequiresIdentityAndEnforcesOwner(t *testing.T) {
	mock := &streamChatServiceMock{expectedUID: 8}
	for _, tc := range []struct {
		name     string
		withUser bool
		want     int
	}{
		{name: "missing identity", want: http.StatusUnauthorized},
		{name: "different owner", withUser: true, want: http.StatusNotFound},
	} {
		t.Run(tc.name, func(t *testing.T) {
			response := httptest.NewRecorder()
			streamTestRouter(mock, tc.withUser).ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/api/agent/sessions/10/turns/turn-1/stream", nil))
			if response.Code != tc.want {
				t.Fatalf("status=%d want=%d body=%s", response.Code, tc.want, response.Body.String())
			}
		})
	}
}

func TestAgentTurnStreamStopsWhenClientCancels(t *testing.T) {
	oldPoll := agentTurnPollInterval
	agentTurnPollInterval = time.Millisecond
	defer func() { agentTurnPollInterval = oldPoll }()
	mock := &streamChatServiceMock{expectedUID: 7, cancelSeen: make(chan struct{})}
	ctx, cancel := context.WithCancel(context.Background())
	req := httptest.NewRequest(http.MethodGet, "/api/agent/sessions/10/turns/turn-1/stream", nil).WithContext(ctx)
	done := make(chan struct{})
	go func() {
		streamTestRouter(mock, true).ServeHTTP(httptest.NewRecorder(), req)
		close(done)
	}()
	for mock.calls.Load() == 0 {
		time.Sleep(time.Millisecond)
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("stream handler did not exit after client cancellation")
	}
}
