package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type DecoctionHandler struct {
	svc *service.DecoctionService
}

func NewDecoctionHandler() *DecoctionHandler {
	return &DecoctionHandler{svc: service.NewDecoctionService()}
}

// List godoc
// @Summary      获取方剂列表
// @Description  分页查询方剂，支持关键词搜索
// @Tags         decoctions
// @Accept       json
// @Produce      json
// @Param        page       query      int     false  "页码"      default(1)
// @Param        page_size  query      int     false  "每页数量"   default(20)
// @Param        keyword    query      string  false  "搜索关键词"
// @Success      200  {object}  object{data=[]model.DecoctionBasic,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Router       /api/decoctions [get]
func (h *DecoctionHandler) List(c *gin.Context) {
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
// @Summary      获取方剂详情
// @Description  根据 ID 获取方剂详细信息，包括组成和主治
// @Tags         decoctions
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "方剂 ID"
// @Success      200  {object}  object{data=service.DecoctionDetail}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /api/decoctions/{id} [get]
func (h *DecoctionHandler) Detail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if !requirePublicDetailAccess(c, "decoction_basic", id) {
		return
	}
	detail, err := h.svc.GetDetail(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该方剂"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}

// Create godoc
// @Summary      创建方剂
// @Description  管理员新增方剂记录
// @Tags         decoctions
// @Accept       json
// @Produce      json
// @Param        decoction  body      model.DecoctionBasic  true  "方剂信息"
// @Success      201  {object}  object{data=model.DecoctionBasic}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/decoctions [post]
func (h *DecoctionHandler) Create(c *gin.Context) {
	var item model.DecoctionBasic
	if err := c.ShouldBindJSON(&item); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if item.DecoctionName == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "方剂名称不能为空"})
		return
	}
	if err := h.svc.Create(&item); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"data": item})
}

// Update godoc
// @Summary      更新方剂
// @Description  管理员更新现有方剂记录
// @Tags         decoctions
// @Accept       json
// @Produce      json
// @Param        id         path      int                   true  "方剂 ID"
// @Param        decoction  body      model.DecoctionBasic  true  "方剂信息"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/decoctions/{id} [put]
func (h *DecoctionHandler) Update(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	var item model.DecoctionBasic
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
// @Summary      删除方剂
// @Description  管理员删除指定方剂记录
// @Tags         decoctions
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "方剂 ID"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/decoctions/{id} [delete]
func (h *DecoctionHandler) Delete(c *gin.Context) {
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
