package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type HerbHandler struct {
	svc *service.HerbService
}

func NewHerbHandler() *HerbHandler { return &HerbHandler{svc: service.NewHerbService()} }

// ListHerbs godoc
// @Summary      获取单味药列表
// @Description  分页查询单味药，支持关键词搜索
// @Tags         herbs
// @Accept       json
// @Produce      json
// @Param        page       query      int     false  "页码"      default(1)
// @Param        page_size  query      int     false  "每页数量"   default(20)
// @Param        keyword    query      string  false  "搜索关键词"
// @Success      200  {object}  object{data=[]model.HerbBasic,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Router       /herbs [get]
func (h *HerbHandler) List(c *gin.Context) {
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

// GetHerbDetail godoc
// @Summary      获取单味药详情
// @Description  根据 ID 获取单味药详细信息，包括毒性成分和名家经验
// @Tags         herbs
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "药物 ID"
// @Success      200  {object}  object{data=service.HerbDetail}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /herbs/{id} [get]
func (h *HerbHandler) Detail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	detail, err := h.svc.GetDetail(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该药物"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}

func (h *HerbHandler) Create(c *gin.Context) {
	var herb model.HerbBasic
	if err := c.ShouldBindJSON(&herb); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if herb.HerbName == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "药物名称不能为空"})
		return
	}
	if err := h.svc.Create(&herb); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"data": herb})
}

func (h *HerbHandler) Update(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	var herb model.HerbBasic
	if err := c.ShouldBindJSON(&herb); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	herb.ID = id
	if err := h.svc.Update(&herb); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "更新成功"})
}

func (h *HerbHandler) Delete(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if err := h.svc.Delete(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "删除成功"})
}
