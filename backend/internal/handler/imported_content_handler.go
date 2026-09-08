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
