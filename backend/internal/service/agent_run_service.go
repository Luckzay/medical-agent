package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	agentclient "medicalagent/internal/client/agent"
	"medicalagent/internal/model"
	"medicalagent/internal/repository"

	"gorm.io/gorm"
)

var (
	ErrAgentRunNotFound    = errors.New("agent run not found")
	ErrAgentRunConflict    = errors.New("agent run state conflicts with requested operation")
	ErrAgentUpstream       = errors.New("agent service unavailable")
	ErrIdempotencyConflict = errors.New("idempotency key was already used with a different request")
)

type CreateAgentRunInput struct {
	UserID         int
	Herbs          []string
	ResearchGoal   string
	IdempotencyKey string
}

type AgentRunService struct {
	repo   repository.AgentRunRepository
	client agentclient.Client
}

func NewAgentRunService(repo repository.AgentRunRepository, client agentclient.Client) *AgentRunService {
	return &AgentRunService{repo: repo, client: client}
}

func (s *AgentRunService) Create(ctx context.Context, input CreateAgentRunInput) (model.AgentRunResponse, error) {
	input = normalizeCreateInput(input)
	requestHash, err := hashCreateInput(input)
	if err != nil {
		return model.AgentRunResponse{}, err
	}
	key := input.IdempotencyKey
	if key != "" {
		existing, lookupErr := s.repo.GetByIdempotencyKeyAndUserID(ctx, key, input.UserID)
		if lookupErr == nil {
			return s.idempotentResponse(ctx, existing, requestHash)
		}
		if !errors.Is(lookupErr, gorm.ErrRecordNotFound) {
			return model.AgentRunResponse{}, fmt.Errorf("query idempotent agent run: %w", lookupErr)
		}
	}

	herbsJSON, err := model.EncodeHerbs(input.Herbs)
	if err != nil {
		return model.AgentRunResponse{}, err
	}
	runID, err := secureID("run")
	if err != nil {
		return model.AgentRunResponse{}, err
	}
	traceID, err := secureID("trace")
	if err != nil {
		return model.AgentRunResponse{}, err
	}

	run := &model.AgentRun{
		RunID:        runID,
		UserID:       input.UserID,
		TraceID:      traceID,
		RequestHash:  requestHash,
		HerbsJSON:    herbsJSON,
		ResearchGoal: input.ResearchGoal,
		Status:       model.AgentRunStatusPending,
	}
	if key != "" {
		run.IdempotencyKey = &key
	}
	if err := s.repo.Create(ctx, run); err != nil {
		// A concurrent request may have inserted the same user/key pair.
		if key != "" {
			existing, lookupErr := s.repo.GetByIdempotencyKeyAndUserID(ctx, key, input.UserID)
			if lookupErr == nil {
				return s.idempotentResponse(ctx, existing, requestHash)
			}
		}
		return model.AgentRunResponse{}, fmt.Errorf("create pending agent run: %w", err)
	}

	remote, dispatchErr := s.client.CreateRun(ctx, agentclient.CreateRunRequest{
		RunID: run.RunID, UserID: run.UserID, TraceID: run.TraceID,
		Herbs: input.Herbs, ResearchGoal: input.ResearchGoal,
	})
	if dispatchErr != nil {
		return s.handleDispatchError(ctx, run, dispatchErr)
	}
	return s.converge(ctx, run, remote)
}

func (s *AgentRunService) Get(ctx context.Context, runID string, userID int) (model.AgentRunResponse, error) {
	run, err := s.repo.GetByRunIDAndUserID(ctx, runID, userID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return model.AgentRunResponse{}, ErrAgentRunNotFound
	}
	if err != nil {
		return model.AgentRunResponse{}, fmt.Errorf("get agent run: %w", err)
	}
	return s.reconcile(ctx, run)
}

func (s *AgentRunService) Resume(ctx context.Context, runID string, userID int) (model.AgentRunResponse, error) {
	run, err := s.repo.GetByRunIDAndUserID(ctx, runID, userID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return model.AgentRunResponse{}, ErrAgentRunNotFound
	}
	if err != nil {
		return model.AgentRunResponse{}, fmt.Errorf("get agent run for resume: %w", err)
	}
	if run.Status != model.AgentRunStatusFailed {
		return model.AgentRunResponse{}, fmt.Errorf("%w: only failed runs can be resumed", ErrAgentRunConflict)
	}

	remote, err := s.client.ResumeRun(ctx, run.RunID, run.TraceID)
	if err != nil {
		var httpErr *agentclient.HTTPError
		if errors.As(err, &httpErr) && httpErr.StatusCode == http.StatusConflict {
			return model.AgentRunResponse{}, fmt.Errorf("%w: agent service rejected resume: %v", ErrAgentRunConflict, err)
		}
		return model.AgentRunResponse{}, fmt.Errorf("%w: resume agent run: %w", ErrAgentUpstream, err)
	}
	return s.converge(ctx, run, remote)
}

func (s *AgentRunService) handleDispatchError(ctx context.Context, run *model.AgentRun, dispatchErr error) (model.AgentRunResponse, error) {
	var httpErr *agentclient.HTTPError
	uncertain := !errors.As(dispatchErr, &httpErr) || uncertainHTTPStatus(httpErr.StatusCode)
	if uncertain {
		reconcileCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
		defer cancel()
		remote, reconcileErr := s.client.GetRun(reconcileCtx, run.RunID, run.TraceID)
		if reconcileErr == nil {
			return s.converge(reconcileCtx, run, remote)
		}
		s.updateStatus(reconcileCtx, run.RunID, run.UserID, model.AgentRunStatusDispatchUnknown, "agent dispatch outcome is unknown")
	} else {
		s.updateStatus(ctx, run.RunID, run.UserID, model.AgentRunStatusFailed, "agent service rejected request")
	}
	// Wrap both sentinels so callers can use errors.Is and errors.As to inspect
	// the original network or HTTP error, including its status code.
	return model.AgentRunResponse{}, fmt.Errorf("%w: %w", ErrAgentUpstream, dispatchErr)
}

func (s *AgentRunService) converge(ctx context.Context, run *model.AgentRun, remote *agentclient.RunResponse) (model.AgentRunResponse, error) {
	status := remote.Status
	if !validAgentRunStatus(status) || status == model.AgentRunStatusDispatchUnknown {
		status = model.AgentRunStatusRunning
	}
	if err := s.repo.UpdateResult(ctx, run.RunID, run.UserID, status, remote.ErrorMessage, remote.AnalysisResult, remote.Workflow); err != nil {
		return model.AgentRunResponse{}, fmt.Errorf("update agent run result: %w", err)
	}
	updated, err := s.repo.GetByRunIDAndUserID(ctx, run.RunID, run.UserID)
	if err != nil {
		return model.AgentRunResponse{}, fmt.Errorf("reload agent run: %w", err)
	}
	return updated.Response()
}

func (s *AgentRunService) updateStatus(ctx context.Context, runID string, userID int, status, message string) {
	updateCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	_ = s.repo.UpdateResult(updateCtx, runID, userID, status, &message, nil, nil)
}

func normalizeCreateInput(input CreateAgentRunInput) CreateAgentRunInput {
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	input.ResearchGoal = strings.TrimSpace(input.ResearchGoal)
	normalizedHerbs := make([]string, len(input.Herbs))
	for i, herb := range input.Herbs {
		normalizedHerbs[i] = strings.TrimSpace(herb)
	}
	input.Herbs = normalizedHerbs
	return input
}

func hashCreateInput(input CreateAgentRunInput) (string, error) {
	canonical := struct {
		Herbs        []string `json:"herbs"`
		ResearchGoal string   `json:"research_goal"`
	}{Herbs: input.Herbs, ResearchGoal: input.ResearchGoal}
	data, err := json.Marshal(canonical)
	if err != nil {
		return "", fmt.Errorf("marshal request hash input: %w", err)
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

func (s *AgentRunService) idempotentResponse(ctx context.Context, run *model.AgentRun, requestHash string) (model.AgentRunResponse, error) {
	if run.RequestHash != requestHash {
		return model.AgentRunResponse{}, ErrIdempotencyConflict
	}
	return s.reconcile(ctx, run)
}

func (s *AgentRunService) reconcile(ctx context.Context, run *model.AgentRun) (model.AgentRunResponse, error) {
	if run.Status != model.AgentRunStatusPending && run.Status != model.AgentRunStatusRunning && run.Status != model.AgentRunStatusDispatchUnknown {
		return run.Response()
	}
	reconcileCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	remote, err := s.client.GetRun(reconcileCtx, run.RunID, run.TraceID)
	if err == nil && remote != nil {
		if response, convergeErr := s.converge(reconcileCtx, run, remote); convergeErr == nil {
			return response, nil
		}
	}
	// Reconciliation is best-effort for reads and idempotent retries. Keep the
	// durable local state and return it rather than turning a read into 5xx.
	return run.Response()
}

func secureID(prefix string) (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", fmt.Errorf("generate %s id: %w", prefix, err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf("%s_%x%x%x%x%x", prefix, value[0:4], value[4:6], value[6:8], value[8:10], value[10:16]), nil
}

func uncertainHTTPStatus(status int) bool {
	return status == http.StatusConflict || status == http.StatusRequestTimeout || status >= http.StatusInternalServerError
}

func validAgentRunStatus(status string) bool {
	switch status {
	case model.AgentRunStatusPending, model.AgentRunStatusRunning, model.AgentRunStatusCompleted,
		model.AgentRunStatusFailed, model.AgentRunStatusCancelled, model.AgentRunStatusDispatchUnknown:
		return true
	default:
		return false
	}
}
