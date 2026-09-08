package handler

import (
	"errors"
	"net/http"

	"medicalagent/internal/service"
	"medicalagent/internal/util"

	"github.com/gin-gonic/gin"
)

type KnowledgeHandler struct {
	svc   *service.KnowledgeService
	token string
}

func NewKnowledgeHandler(svc *service.KnowledgeService, token string) *KnowledgeHandler {
	return &KnowledgeHandler{svc: svc, token: token}
}

type knowledgeSearchRequest struct {
	Query string   `json:"query"`
	Types []string `json:"types"`
	Limit int      `json:"limit"`
}

func (h *KnowledgeHandler) Search(c *gin.Context) {
	if h.token == "" || !util.ConstantTimeCompare(c.GetHeader("X-Agent-Token"), h.token) {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized internal access"})
		return
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 64<<10)
	var req knowledgeSearchRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求 JSON 无效"})
		return
	}
	results, err := h.svc.Search(c.Request.Context(), req.Query, req.Types, req.Limit)
	if errors.Is(err, service.ErrInvalidKnowledgeSearch) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "query、types 或 limit 无效"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "知识库搜索失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"results": results})
}
