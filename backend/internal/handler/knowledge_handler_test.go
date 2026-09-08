package handler

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"medicalagent/internal/repository"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type handlerKnowledgeRepo struct{}

func (*handlerKnowledgeRepo) Search(context.Context, string, []string, int) ([]repository.KnowledgeResult, error) {
	return []repository.KnowledgeResult{}, nil
}

func TestKnowledgeSearchRequiresInternalToken(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := NewKnowledgeHandler(service.NewKnowledgeService(&handlerKnowledgeRepo{}), "secret")
	router := gin.New()
	router.POST("/internal/v1/knowledge/search", handler.Search)

	for _, tc := range []struct {
		token string
		code  int
	}{{"", http.StatusUnauthorized}, {"wrong", http.StatusUnauthorized}, {"secret", http.StatusOK}} {
		request := httptest.NewRequest(http.MethodPost, "/internal/v1/knowledge/search", bytes.NewBufferString(`{"query":"黄芪"}`))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Agent-Token", tc.token)
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)
		if response.Code != tc.code {
			t.Fatalf("token %q: got %d, want %d: %s", tc.token, response.Code, tc.code, response.Body.String())
		}
	}
}
