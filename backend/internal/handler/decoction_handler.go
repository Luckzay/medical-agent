package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type DecoctionHandler struct {
	svc *service.DecoctionService
}

func NewDecoctionHandler() *DecoctionHandler {
	return &DecoctionHandler{svc: service.NewDecoctionService()}
}

func (h *DecoctionHandler) List(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	keyword := c.Query("keyword")
	if page < 1 { page = 1 }
	if pageSize < 1 { pageSize = 20 }

	list, total, err := h.svc.List(page, pageSize, keyword)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": list, "total": total, "page": page, "page_size": pageSize})
}

func (h *DecoctionHandler) Detail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	detail, err := h.svc.GetDetail(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该方剂"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}
