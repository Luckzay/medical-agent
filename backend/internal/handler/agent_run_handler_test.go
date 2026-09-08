package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type handlerAgentRunServiceMock struct {
	createInput  service.CreateAgentRunInput
	createErr    error
	getUserID    int
	resumeRunID  string
	resumeUserID int
	resumeErr    error
}

func (m *handlerAgentRunServiceMock) Create(_ context.Context, input service.CreateAgentRunInput) (model.AgentRunResponse, error) {
	m.createInput = input
	return model.AgentRunResponse{RunID: "run-1", UserID: input.UserID, Herbs: input.Herbs, Status: "running"}, m.createErr
}
func (m *handlerAgentRunServiceMock) Get(_ context.Context, _ string, userID int) (model.AgentRunResponse, error) {
	m.getUserID = userID
	return model.AgentRunResponse{}, service.ErrAgentRunNotFound
}
func (m *handlerAgentRunServiceMock) Resume(_ context.Context, runID string, userID int) (model.AgentRunResponse, error) {
	m.resumeRunID = runID
	m.resumeUserID = userID
	return model.AgentRunResponse{RunID: runID, UserID: userID, Status: model.AgentRunStatusRunning}, m.resumeErr
}

func TestAgentRunHandlerCreate(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mock := &handlerAgentRunServiceMock{}
	router := gin.New()
	router.POST("/runs", func(c *gin.Context) {
		c.Set("user_id", 42)
		c.Next()
	}, NewAgentRunHandler(mock).Create)

	req := httptest.NewRequest(http.MethodPost, "/runs", strings.NewReader(`{"herbs":[" 黄芪 "],"research_goal":"研究"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", "key-1")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, req)

	if response.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if mock.createInput.UserID != 42 || mock.createInput.Herbs[0] != "黄芪" || mock.createInput.IdempotencyKey != "key-1" {
		t.Fatalf("unexpected service input: %+v", mock.createInput)
	}
}

func TestAgentRunHandlerValidationAndUpstreamError(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mock := &handlerAgentRunServiceMock{createErr: service.ErrAgentUpstream}
	router := gin.New()
	router.POST("/runs", func(c *gin.Context) { c.Set("user_id", 42) }, NewAgentRunHandler(mock).Create)

	invalid := httptest.NewRecorder()
	router.ServeHTTP(invalid, httptest.NewRequest(http.MethodPost, "/runs", strings.NewReader(`{"herbs":[]}`)))
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("invalid status=%d", invalid.Code)
	}

	req := httptest.NewRequest(http.MethodPost, "/runs", strings.NewReader(`{"herbs":["黄芪"]}`))
	req.Header.Set("Content-Type", "application/json")
	upstream := httptest.NewRecorder()
	router.ServeHTTP(upstream, req)
	if upstream.Code != http.StatusBadGateway {
		t.Fatalf("upstream status=%d body=%s", upstream.Code, upstream.Body.String())
	}
}

func TestAgentRunHandlerGetUsesCurrentUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mock := &handlerAgentRunServiceMock{}
	router := gin.New()
	router.GET("/runs/:run_id", func(c *gin.Context) { c.Set("user_id", 77) }, NewAgentRunHandler(mock).Get)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/runs/run-1", nil))
	if response.Code != http.StatusNotFound || mock.getUserID != 77 {
		t.Fatalf("status=%d userID=%d", response.Code, mock.getUserID)
	}
}

func TestAgentRunHandlerIdempotencyConflict(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mock := &handlerAgentRunServiceMock{createErr: service.ErrIdempotencyConflict}
	router := gin.New()
	router.POST("/runs", func(c *gin.Context) { c.Set("user_id", 42) }, NewAgentRunHandler(mock).Create)
	req := httptest.NewRequest(http.MethodPost, "/runs", strings.NewReader(`{"herbs":["黄芪"]}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", "key-1")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, req)
	if response.Code != http.StatusConflict {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestAgentRunHandlerResumeUsesCurrentUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mock := &handlerAgentRunServiceMock{}
	router := gin.New()
	router.POST("/runs/:run_id/resume", func(c *gin.Context) { c.Set("user_id", 77) }, NewAgentRunHandler(mock).Resume)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/runs/run-1/resume", nil))
	if response.Code != http.StatusOK || mock.resumeRunID != "run-1" || mock.resumeUserID != 77 {
		t.Fatalf("status=%d runID=%s userID=%d body=%s", response.Code, mock.resumeRunID, mock.resumeUserID, response.Body.String())
	}
}

func TestAgentRunHandlerResumeErrorMapping(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want int
	}{
		{name: "not found", err: service.ErrAgentRunNotFound, want: http.StatusNotFound},
		{name: "conflict", err: service.ErrAgentRunConflict, want: http.StatusConflict},
		{name: "upstream", err: service.ErrAgentUpstream, want: http.StatusBadGateway},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			mock := &handlerAgentRunServiceMock{resumeErr: tc.err}
			router := gin.New()
			router.POST("/runs/:run_id/resume", func(c *gin.Context) { c.Set("user_id", 77) }, NewAgentRunHandler(mock).Resume)
			response := httptest.NewRecorder()
			router.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/runs/run-1/resume", nil))
			if response.Code != tc.want {
				t.Fatalf("status=%d want=%d body=%s", response.Code, tc.want, response.Body.String())
			}
		})
	}
}
