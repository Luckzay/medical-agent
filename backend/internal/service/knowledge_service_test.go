package service

import (
	"context"
	"errors"
	"testing"

	"medicalagent/internal/repository"
)

type knowledgeRepoMock struct {
	called bool
	types  []string
	limit  int
}

func (m *knowledgeRepoMock) Search(_ context.Context, _ string, types []string, limit int) ([]repository.KnowledgeResult, error) {
	m.called, m.types, m.limit = true, types, limit
	return []repository.KnowledgeResult{}, nil
}

func TestKnowledgeSearchValidationAndDefaults(t *testing.T) {
	repo := &knowledgeRepoMock{}
	svc := NewKnowledgeService(repo)
	results, err := svc.Search(context.Background(), "黄芪", nil, 0)
	if err != nil || results == nil || !repo.called || len(repo.types) != 5 || repo.limit != 10 {
		t.Fatalf("unexpected result=%v err=%v repo=%+v", results, err, repo)
	}
	for _, tc := range []struct {
		query string
		types []string
		limit int
	}{{"", nil, 1}, {"x", []string{"users"}, 1}, {"x", nil, MaxKnowledgeLimit + 1}} {
		if _, err := svc.Search(context.Background(), tc.query, tc.types, tc.limit); !errors.Is(err, ErrInvalidKnowledgeSearch) {
			t.Fatalf("expected validation error for %+v, got %v", tc, err)
		}
	}
}
