package agent

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type CreateRunRequest struct {
	RunID        string   `json:"run_id"`
	UserID       int      `json:"user_id"`
	TraceID      string   `json:"trace_id"`
	Herbs        []string `json:"herbs"`
	ResearchGoal string   `json:"research_goal"`
}

type RunResponse struct {
	RunID          string          `json:"run_id"`
	UserID         int             `json:"user_id"`
	TraceID        string          `json:"trace_id"`
	Herbs          []string        `json:"herbs"`
	ResearchGoal   string          `json:"research_goal"`
	Status         string          `json:"status"`
	ErrorMessage   *string         `json:"error_message"`
	AnalysisResult json.RawMessage `json:"analysis_result"`
	Workflow       json.RawMessage `json:"workflow"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
}

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type CreateTurnRequest struct {
	TurnID    string        `json:"turn_id"`
	SessionID string        `json:"session_id"`
	UserID    string        `json:"user_id"`
	Message   string        `json:"message"`
	History   []ChatMessage `json:"history"`
}

type TurnResponse struct {
	TurnID           string          `json:"turn_id"`
	SessionID        string          `json:"session_id"`
	Status           string          `json:"status"`
	Events           json.RawMessage `json:"events"`
	AssistantMessage string          `json:"assistant_message"`
	ErrorMessage     string          `json:"error_message"`
	CreatedAt        time.Time       `json:"created_at"`
	UpdatedAt        time.Time       `json:"updated_at"`
}

type Client interface {
	CreateRun(ctx context.Context, request CreateRunRequest) (*RunResponse, error)
	GetRun(ctx context.Context, runID, traceID string) (*RunResponse, error)
	ResumeRun(ctx context.Context, runID, traceID string) (*RunResponse, error)
}

type ChatClient interface {
	CreateTurn(ctx context.Context, request CreateTurnRequest) (*TurnResponse, error)
	GetTurn(ctx context.Context, turnID string) (*TurnResponse, error)
}

type HTTPError struct {
	StatusCode int
	Body       string
}

func (e *HTTPError) Error() string {
	return fmt.Sprintf("agent service returned HTTP %d: %s", e.StatusCode, e.Body)
}

type HTTPClient struct {
	baseURL       string
	internalToken string
	client        *http.Client
}

func NewHTTPClient(baseURL, internalToken string, timeout time.Duration) *HTTPClient {
	return &HTTPClient{baseURL: strings.TrimRight(baseURL, "/"), internalToken: internalToken, client: &http.Client{Timeout: timeout}}
}

func (c *HTTPClient) CreateRun(ctx context.Context, request CreateRunRequest) (*RunResponse, error) {
	var result RunResponse
	if err := c.doJSON(ctx, http.MethodPost, c.baseURL+"/internal/v1/runs", request.TraceID, request, &result); err != nil {
		return nil, err
	}
	cleanRunResponse(&result)
	return &result, nil
}

func (c *HTTPClient) GetRun(ctx context.Context, runID, traceID string) (*RunResponse, error) {
	var result RunResponse
	endpoint := c.baseURL + "/internal/v1/runs/" + url.PathEscape(runID)
	if err := c.doJSON(ctx, http.MethodGet, endpoint, traceID, nil, &result); err != nil {
		return nil, err
	}
	cleanRunResponse(&result)
	return &result, nil
}

func (c *HTTPClient) ResumeRun(ctx context.Context, runID, traceID string) (*RunResponse, error) {
	var result RunResponse
	endpoint := c.baseURL + "/internal/v1/runs/" + url.PathEscape(runID) + "/resume"
	if err := c.doJSON(ctx, http.MethodPost, endpoint, traceID, nil, &result); err != nil {
		return nil, err
	}
	cleanRunResponse(&result)
	return &result, nil
}

func (c *HTTPClient) CreateTurn(ctx context.Context, request CreateTurnRequest) (*TurnResponse, error) {
	var result TurnResponse
	if err := c.doJSON(ctx, http.MethodPost, c.baseURL+"/internal/v1/chat/turns", request.TurnID, request, &result); err != nil {
		return nil, err
	}
	cleanTurnResponse(&result)
	return &result, nil
}

func (c *HTTPClient) GetTurn(ctx context.Context, turnID string) (*TurnResponse, error) {
	var result TurnResponse
	endpoint := c.baseURL + "/internal/v1/chat/turns/" + url.PathEscape(turnID)
	if err := c.doJSON(ctx, http.MethodGet, endpoint, turnID, nil, &result); err != nil {
		return nil, err
	}
	cleanTurnResponse(&result)
	return &result, nil
}

func (c *HTTPClient) doJSON(ctx context.Context, method, endpoint, traceID string, input, output any) error {
	var body io.Reader
	if input != nil {
		encoded, err := json.Marshal(input)
		if err != nil {
			return fmt.Errorf("marshal agent request: %w", err)
		}
		body = bytes.NewReader(encoded)
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, body)
	if err != nil {
		return fmt.Errorf("build agent service request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("X-Trace-ID", traceID)
	req.Header.Set("X-Agent-Token", c.internalToken)
	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("call agent service: %w", err)
	}
	defer resp.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return fmt.Errorf("read agent service response: %w", err)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return &HTTPError{StatusCode: resp.StatusCode, Body: strings.TrimSpace(string(responseBody))}
	}
	if err := json.Unmarshal(responseBody, output); err != nil {
		return fmt.Errorf("decode agent service response: %w", err)
	}
	return nil
}

func cleanRunResponse(result *RunResponse) {
	if bytes.Equal(bytes.TrimSpace(result.AnalysisResult), []byte("null")) {
		result.AnalysisResult = nil
	}
	if bytes.Equal(bytes.TrimSpace(result.Workflow), []byte("null")) {
		result.Workflow = nil
	}
}

func cleanTurnResponse(result *TurnResponse) {
	if len(bytes.TrimSpace(result.Events)) == 0 || bytes.Equal(bytes.TrimSpace(result.Events), []byte("null")) {
		result.Events = json.RawMessage("[]")
	}
}
