package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type CoupletHandler struct {
	svc *service.CoupletService
}

func NewCoupletHandler() *CoupletHandler {
	return &CoupletHandler{svc: service.NewCoupletService()}
}

// List godoc
// @Summary      获取药对列表
// @Description  分页查询药对，支持关键词搜索
// @Tags         couplets
// @Accept       json
// @Produce      json
// @Param        page       query      int     false  "页码"      default(1)
// @Param        page_size  query      int     false  "每页数量"   default(20)
// @Param        keyword    query      string  false  "搜索关键词"
// @Success      200  {object}  object{data=[]model.HerbCoupletBasic,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Router       /api/couplets [get]
func (h *CoupletHandler) List(c *gin.Context) {
	page, pageSize, guest := publicPagination(c)
	keyword := c.Query("keyword")

	list, total, err := h.svc.List(page, pageSize, keyword)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": list, "total": publicTotal(total, guest), "page": page, "page_size": pageSize})
}

// Detail godoc
// @Summary      获取药对详情
// @Description  根据 ID 获取药对详细信息，包括组成和研究进展
// @Tags         couplets
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "药对 ID"
// @Success      200  {object}  object{data=service.CoupletDetail}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /api/couplets/{id} [get]
func (h *CoupletHandler) Detail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if !requirePublicDetailAccess(c, "herb_couplet_basic", id) {
		return
	}
	detail, err := h.svc.GetDetail(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该药对"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}

// Create godoc
// @Summary      创建药对
// @Description  管理员新增药对记录
// @Tags         couplets
// @Accept       json
// @Produce      json
// @Param        couplet  body      model.HerbCoupletBasic  true  "药对信息"
// @Success      201  {object}  object{data=model.HerbCoupletBasic}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/couplets [post]
func (h *CoupletHandler) Create(c *gin.Context) {
	var item model.HerbCoupletBasic
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

// Update godoc
// @Summary      更新药对
// @Description  管理员更新现有药对记录
// @Tags         couplets
// @Accept       json
// @Produce      json
// @Param        id       path      int                     true  "药对 ID"
// @Param        couplet  body      model.HerbCoupletBasic  true  "药对信息"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/couplets/{id} [put]
func (h *CoupletHandler) Update(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	var item model.HerbCoupletBasic
	if err := c.ShouldBindJSON(&item); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	item.ID = id
	if err := h.svc.Update(&item); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "更新成功"})
}

// Delete godoc
// @Summary      删除药对
// @Description  管理员删除指定药对记录
// @Tags         couplets
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "药对 ID"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/couplets/{id} [delete]
func (h *CoupletHandler) Delete(c *gin.Context) {
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
