package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type CompoundHandler struct {
	svc *service.CompoundService
}

func NewCompoundHandler() *CompoundHandler {
	return &CompoundHandler{svc: service.NewCompoundService()}
}

func (h *CompoundHandler) List(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	keyword := c.Query("keyword")
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 20
	}

	list, total, err := h.svc.List(page, pageSize, keyword)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": list, "total": total, "page": page, "page_size": pageSize})
}

func (h *CompoundHandler) Detail(c *gin.Context) {
	rn, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	detail, err := h.svc.GetByRecordNumber(rn)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该化合物"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}

func (h *CompoundHandler) Create(c *gin.Context) {
	var item model.MolecularInfo
	if err := c.ShouldBindJSON(&item); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.svc.Create(&item); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"data": item})
}

func (h *CompoundHandler) Update(c *gin.Context) {
	rn, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	var item model.MolecularInfo
	if err := c.ShouldBindJSON(&item); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	item.RecordNumber = rn
	if err := h.svc.Update(&item); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "更新成功"})
}

func (h *CompoundHandler) Delete(c *gin.Context) {
	rn, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if err := h.svc.Delete(rn); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "删除成功"})
}
