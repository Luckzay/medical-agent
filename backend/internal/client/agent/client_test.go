package agent

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestHTTPClientCreateRunSendsInternalHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/internal/v1/runs" {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		if got := r.Header.Get("X-Trace-ID"); got != "trace-1" {
			t.Fatalf("X-Trace-ID = %q", got)
		}
		if got := r.Header.Get("X-Agent-Token"); got != "secret-token" {
			t.Fatalf("X-Agent-Token = %q", got)
		}
		var request CreateRunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if request.RunID != "run-1" || request.UserID != 7 || len(request.Herbs) != 1 {
			t.Fatalf("unexpected request body: %+v", request)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"run_id":"run-1","user_id":7,"trace_id":"trace-1","herbs":["黄芪"],"research_goal":"goal","status":"completed","analysis_result":{"schema_version":"1.0","compounds":[]},"created_at":"2026-08-08T04:00:00Z","updated_at":"2026-08-08T04:00:00Z"}`))
	}))
	defer server.Close()

	client := NewHTTPClient(server.URL+"/", "secret-token", time.Second)
	response, err := client.CreateRun(context.Background(), CreateRunRequest{
		RunID: "run-1", UserID: 7, TraceID: "trace-1", Herbs: []string{"黄芪"}, ResearchGoal: "goal",
	})
	if err != nil {
		t.Fatal(err)
	}
	if response.Status != "completed" || response.RunID != "run-1" || string(response.AnalysisResult) != `{"schema_version":"1.0","compounds":[]}` {
		t.Fatalf("unexpected response: %+v", response)
	}
}

func TestHTTPClientGetRun(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/internal/v1/runs/run-1" {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("X-Agent-Token") != "secret-token" || r.Header.Get("X-Trace-ID") != "trace-1" {
			t.Fatalf("missing internal headers")
		}
		_, _ = w.Write([]byte(`{"run_id":"run-1","user_id":7,"trace_id":"trace-1","herbs":["黄芪"],"research_goal":"","status":"completed","created_at":"2026-08-08T04:00:00Z","updated_at":"2026-08-08T04:00:00Z"}`))
	}))
	defer server.Close()

	response, err := NewHTTPClient(server.URL, "secret-token", time.Second).GetRun(context.Background(), "run-1", "trace-1")
	if err != nil || response.Status != "completed" {
		t.Fatalf("response=%+v err=%v", response, err)
	}
}

func TestHTTPClientReturnsStructuredError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, `{"detail":"invalid herbs"}`, http.StatusUnprocessableEntity)
	}))
	defer server.Close()

	_, err := NewHTTPClient(server.URL, "token", time.Second).CreateRun(context.Background(), CreateRunRequest{TraceID: "trace-1"})
	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("expected HTTPError, got %T: %v", err, err)
	}
	if httpErr.StatusCode != http.StatusUnprocessableEntity || httpErr.Body == "" {
		t.Fatalf("unexpected HTTPError: %+v", httpErr)
	}
}

func TestHTTPClientResumeRunSendsHeadersPathAndNoBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.EscapedPath() != "/internal/v1/runs/run-1/resume" {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.EscapedPath())
		}
		if r.Header.Get("X-Agent-Token") != "secret-token" || r.Header.Get("X-Trace-ID") != "trace-1" {
			t.Fatalf("missing internal headers")
		}
		if r.Body != http.NoBody && r.ContentLength != 0 {
			t.Fatalf("resume request must not contain a body: content length=%d", r.ContentLength)
		}
		_, _ = w.Write([]byte(`{"run_id":"run-1","user_id":7,"trace_id":"trace-1","herbs":["黄芪"],"research_goal":"goal","status":"running","error_message":"retrying","analysis_result":{"summary":"partial"},"workflow":{"current_node":"research"},"created_at":"2026-08-08T04:00:00Z","updated_at":"2026-08-08T04:00:01Z"}`))
	}))
	defer server.Close()

	response, err := NewHTTPClient(server.URL, "secret-token", time.Second).ResumeRun(context.Background(), "run-1", "trace-1")
	if err != nil {
		t.Fatal(err)
	}
	if response.ErrorMessage == nil || *response.ErrorMessage != "retrying" || string(response.Workflow) != `{"current_node":"research"}` {
		t.Fatalf("unexpected response: %+v", response)
	}
}

func TestHTTPClientCreateTurnUsesPythonContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/internal/v1/chat/turns" {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("X-Agent-Token") != "secret-token" {
			t.Fatal("missing internal token")
		}
		var request CreateTurnRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if request.SessionID != "3" || request.UserID != "7" || request.Message != "继续" || len(request.History) != 1 {
			t.Fatalf("unexpected request: %+v", request)
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"turn_id":"turn-1","session_id":"3","status":"pending","events":[],"created_at":"2026-08-08T04:00:00Z","updated_at":"2026-08-08T04:00:00Z"}`))
	}))
	defer server.Close()

	response, err := NewHTTPClient(server.URL, "secret-token", time.Second).CreateTurn(context.Background(), CreateTurnRequest{
		TurnID: "turn-1", SessionID: "3", UserID: "7", Message: "继续", History: []ChatMessage{{Role: "user", Content: "之前"}},
	})
	if err != nil || response.Status != "pending" || response.SessionID != "3" {
		t.Fatalf("response=%+v err=%v", response, err)
	}
}
