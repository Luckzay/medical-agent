package handler

import (
	"errors"
	"net/http"
	"strconv"

	"medicalagent/internal/repository"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type ImportedContentHandler struct {
	repo *repository.ImportedContentRepo
	kind string
}

func NewImportedContentHandler(kind string) *ImportedContentHandler {
	return &ImportedContentHandler{repo: repository.NewImportedContentRepo(), kind: kind}
}

// List godoc
// @Summary      获取导入内容列表 (病案/条文)
// @Description  分页查询导入的病案或条文内容
// @Tags         imported
// @Accept       json
// @Produce      json
// @Param        page       query      int  false  "页码"      default(1)
// @Param        page_size  query      int  false  "每页数量"   default(20)
// @Success      200  {object}  object{data=[]map[string]any,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Router       /api/cases [get]
// @Router       /api/clauses [get]
func (h *ImportedContentHandler) List(c *gin.Context) {
	page, pageSize, guest := publicPagination(c)
	list, total, err := h.repo.List(h.kind+"s", page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"data": list, "total": publicTotal(total, guest), "page": page, "page_size": pageSize,
	})
}

// Detail godoc
// @Summary      获取导入内容详情 (病案/条文)
// @Description  根据 ID 获取病案或条文的详细内容及关联信息
// @Tags         imported
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "记录 ID"
// @Success      200  {object}  object{data=object{record=map[string]any,herbs=[]map[string]any,decoctions=[]map[string]any}}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /api/cases/{id} [get]
// @Router       /api/clauses/{id} [get]
func (h *ImportedContentHandler) Detail(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if !requirePublicDetailAccess(c, h.kind+"s", id) {
		return
	}
	record, herbs, decoctions, err := h.repo.Detail(h.kind, id)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到记录"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": gin.H{"record": record, "herbs": herbs, "decoctions": decoctions}})
}
