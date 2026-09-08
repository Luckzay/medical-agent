package service

import (
	"context"
	"errors"
	"strings"

	"medicalagent/internal/repository"
)

const (
	MaxKnowledgeQueryRunes = 200
	MaxKnowledgeLimit      = 50
)

var ErrInvalidKnowledgeSearch = errors.New("invalid knowledge search")

var allKnowledgeTypes = []string{"herbs", "decoctions", "couplets", "compounds", "papers"}

type KnowledgeService struct {
	repo repository.KnowledgeRepository
}

func NewKnowledgeService(repo repository.KnowledgeRepository) *KnowledgeService {
	return &KnowledgeService{repo: repo}
}

func (s *KnowledgeService) Search(ctx context.Context, query string, types []string, limit int) ([]repository.KnowledgeResult, error) {
	query = strings.TrimSpace(query)
	if query == "" || len([]rune(query)) > MaxKnowledgeQueryRunes {
		return nil, ErrInvalidKnowledgeSearch
	}
	if limit == 0 {
		limit = 10
	}
	if limit < 1 || limit > MaxKnowledgeLimit {
		return nil, ErrInvalidKnowledgeSearch
	}
	if len(types) == 0 {
		types = append([]string(nil), allKnowledgeTypes...)
	}
	if len(types) > len(allKnowledgeTypes) {
		return nil, ErrInvalidKnowledgeSearch
	}
	allowed := make(map[string]bool, len(allKnowledgeTypes))
	for _, kind := range allKnowledgeTypes {
		allowed[kind] = true
	}
	seen := make(map[string]bool, len(types))
	clean := make([]string, 0, len(types))
	for _, kind := range types {
		kind = strings.TrimSpace(kind)
		if !allowed[kind] || seen[kind] {
			return nil, ErrInvalidKnowledgeSearch
		}
		seen[kind] = true
		clean = append(clean, kind)
	}
	return s.repo.Search(ctx, query, clean, limit)
}
