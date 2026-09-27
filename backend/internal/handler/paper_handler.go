package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
)

type PaperHandler struct {
	svc *service.PaperService
}

func NewPaperHandler() *PaperHandler {
	return &PaperHandler{svc: service.NewPaperService()}
}

// List godoc
// @Summary      获取文献列表
// @Description  分页查询文献，支持关键词搜索
// @Tags         papers
// @Accept       json
// @Produce      json
// @Param        page       query      int     false  "页码"      default(1)
// @Param        page_size  query      int     false  "每页数量"   default(20)
// @Param        keyword    query      string  false  "搜索关键词"
// @Success      200  {object}  object{data=[]model.Paper,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Router       /api/papers [get]
func (h *PaperHandler) List(c *gin.Context) {
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
// @Summary      获取文献详情
// @Description  根据 ID 获取文献详细信息
// @Tags         papers
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "文献 ID"
// @Success      200  {object}  object{data=model.Paper}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /api/papers/{id} [get]
func (h *PaperHandler) Detail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if !requirePublicDetailAccess(c, "papers", id) {
		return
	}
	detail, err := h.svc.GetDetail(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该文献"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}

// Create godoc
// @Summary      创建文献
// @Description  管理员新增文献记录
// @Tags         papers
// @Accept       json
// @Produce      json
// @Param        paper  body      model.Paper  true  "文献信息"
// @Success      201  {object}  object{data=model.Paper}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/papers [post]
func (h *PaperHandler) Create(c *gin.Context) {
	var item model.Paper
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
// @Summary      更新文献
// @Description  管理员更新现有文献记录
// @Tags         papers
// @Accept       json
// @Produce      json
// @Param        id     path      int          true  "文献 ID"
// @Param        paper  body      model.Paper  true  "文献信息"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/papers/{id} [put]
func (h *PaperHandler) Update(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	var item model.Paper
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
// @Summary      删除文献
// @Description  管理员删除指定文献记录
// @Tags         papers
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "文献 ID"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/papers/{id} [delete]
func (h *PaperHandler) Delete(c *gin.Context) {
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
