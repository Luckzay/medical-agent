package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	agentclient "medicalagent/internal/client/agent"
	"medicalagent/internal/model"

	"gorm.io/gorm"
)

type agentRunRepoMock struct {
	run       *model.AgentRun
	updateErr error
}

func (m *agentRunRepoMock) Create(_ context.Context, run *model.AgentRun) error {
	m.run = run
	return nil
}
func (m *agentRunRepoMock) GetByRunIDAndUserID(_ context.Context, id string, user int) (*model.AgentRun, error) {
	if m.run == nil || m.run.RunID != id || m.run.UserID != user {
		return nil, gorm.ErrRecordNotFound
	}
	return m.run, nil
}
func (m *agentRunRepoMock) GetByIdempotencyKeyAndUserID(_ context.Context, key string, user int) (*model.AgentRun, error) {
	if m.run == nil || m.run.IdempotencyKey == nil || *m.run.IdempotencyKey != key || m.run.UserID != user {
		return nil, gorm.ErrRecordNotFound
	}
	return m.run, nil
}
func (m *agentRunRepoMock) UpdateResult(_ context.Context, id string, user int, status string, message *string, analysis, workflow json.RawMessage) error {
	if m.updateErr != nil {
		return m.updateErr
	}
	m.run.Status, m.run.AnalysisResultJSON, m.run.WorkflowJSON = status, analysis, workflow
	if message != nil {
		m.run.ErrorMessage = *message
	}
	return nil
}

type agentClientMock struct {
	getCalls, createCalls int
	getResponse           *agentclient.RunResponse
	getErr                error
}

func (m *agentClientMock) CreateRun(_ context.Context, req agentclient.CreateRunRequest) (*agentclient.RunResponse, error) {
	m.createCalls++
	return &agentclient.RunResponse{RunID: req.RunID, UserID: req.UserID, TraceID: req.TraceID, Status: model.AgentRunStatusRunning}, nil
}
func (m *agentClientMock) GetRun(context.Context, string, string) (*agentclient.RunResponse, error) {
	m.getCalls++
	return m.getResponse, m.getErr
}
func (m *agentClientMock) ResumeRun(context.Context, string, string) (*agentclient.RunResponse, error) {
	return nil, errors.New("unused")
}

func TestGetReconcilesRunningToCompleted(t *testing.T) {
	repo := &agentRunRepoMock{run: &model.AgentRun{RunID: "run", UserID: 1, TraceID: "trace", HerbsJSON: `[]`, Status: model.AgentRunStatusRunning}}
	analysis, workflow := json.RawMessage(`{"answer":1}`), json.RawMessage(`{"step":1}`)
	client := &agentClientMock{getResponse: &agentclient.RunResponse{Status: model.AgentRunStatusCompleted, AnalysisResult: analysis, Workflow: workflow}}
	got, err := NewAgentRunService(repo, client).Get(context.Background(), "run", 1)
	if err != nil || got.Status != model.AgentRunStatusCompleted || client.getCalls != 1 {
		t.Fatalf("got=%+v err=%v calls=%d", got, err, client.getCalls)
	}
	if string(repo.run.AnalysisResultJSON) != string(analysis) || string(repo.run.WorkflowJSON) != string(workflow) {
		t.Fatal("remote result was not persisted")
	}
}

func TestGetRunningUpstreamFailureReturnsLocal(t *testing.T) {
	repo := &agentRunRepoMock{run: &model.AgentRun{RunID: "run", UserID: 1, HerbsJSON: `[]`, Status: model.AgentRunStatusRunning}}
	got, err := NewAgentRunService(repo, &agentClientMock{getErr: errors.New("network")}).Get(context.Background(), "run", 1)
	if err != nil || got.Status != model.AgentRunStatusRunning {
		t.Fatalf("got=%+v err=%v", got, err)
	}
}

func TestGetTerminalDoesNotCallUpstream(t *testing.T) {
	for _, status := range []string{model.AgentRunStatusCompleted, model.AgentRunStatusFailed, model.AgentRunStatusCancelled} {
		repo := &agentRunRepoMock{run: &model.AgentRun{RunID: "run", UserID: 1, HerbsJSON: `[]`, Status: status}}
		client := &agentClientMock{}
		got, err := NewAgentRunService(repo, client).Get(context.Background(), "run", 1)
		if err != nil || got.Status != status || client.getCalls != 0 {
			t.Fatalf("status=%s got=%+v err=%v calls=%d", status, got, err, client.getCalls)
		}
	}
}

func TestIdempotentRunningReconciles(t *testing.T) {
	key := "key"
	input := CreateAgentRunInput{UserID: 1, Herbs: []string{"黄芪"}, IdempotencyKey: key}
	hash, _ := hashCreateInput(normalizeCreateInput(input))
	repo := &agentRunRepoMock{run: &model.AgentRun{RunID: "run", UserID: 1, TraceID: "trace", HerbsJSON: `["黄芪"]`, Status: model.AgentRunStatusRunning, IdempotencyKey: &key, RequestHash: hash}}
	client := &agentClientMock{getResponse: &agentclient.RunResponse{Status: model.AgentRunStatusCompleted}}
	got, err := NewAgentRunService(repo, client).Create(context.Background(), input)
	if err != nil || got.Status != model.AgentRunStatusCompleted || client.getCalls != 1 || client.createCalls != 0 {
		t.Fatalf("got=%+v err=%v get=%d create=%d", got, err, client.getCalls, client.createCalls)
	}
}

func TestGetPersistenceFailureReturnsLocal(t *testing.T) {
	repo := &agentRunRepoMock{run: &model.AgentRun{RunID: "run", UserID: 1, HerbsJSON: `[]`, Status: model.AgentRunStatusRunning}, updateErr: errors.New("db")}
	client := &agentClientMock{getResponse: &agentclient.RunResponse{Status: model.AgentRunStatusCompleted}}
	got, err := NewAgentRunService(repo, client).Get(context.Background(), "run", 1)
	if err != nil || got.Status != model.AgentRunStatusRunning {
		t.Fatalf("got=%+v err=%v", got, err)
	}
}
