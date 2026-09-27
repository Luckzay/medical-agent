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
	Query string   `json:"query" example:"麻黄的功效"`
	Types []string `json:"types" example:"herb,decoction"`
	Limit int      `json:"limit" example:"5"`
}

// Search godoc
// @Summary      知识库搜索接口
// @Description  供 Agent 服务内部调用的知识库语义搜索接口
// @Tags         internal
// @Accept       json
// @Produce      json
// @Param        X-Agent-Token  header  string  true  "内部认证令牌"
// @Param        request  body      knowledgeSearchRequest  true  "搜索请求"
// @Success      200  {object}  object{results=[]map[string]any}
// @Failure      400  {object}  object{error=string}
// @Failure      401  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     AgentTokenAuth
// @Router       /internal/v1/knowledge/search [post]
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
