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

// List godoc
// @Summary      获取化合物列表
// @Description  分页查询化合物，支持关键词搜索
// @Tags         compounds
// @Accept       json
// @Produce      json
// @Param        page       query      int     false  "页码"      default(1)
// @Param        page_size  query      int     false  "每页数量"   default(20)
// @Param        keyword    query      string  false  "搜索关键词"
// @Success      200  {object}  object{data=[]model.MolecularInfo,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Router       /api/compounds [get]
func (h *CompoundHandler) List(c *gin.Context) {
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
// @Summary      获取化合物详情
// @Description  根据 Record Number 获取化合物详细信息
// @Tags         compounds
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "Record Number"
// @Success      200  {object}  object{data=model.MolecularInfo}
// @Failure      400  {object}  object{error=string}
// @Failure      404  {object}  object{error=string}
// @Router       /api/compounds/{id} [get]
func (h *CompoundHandler) Detail(c *gin.Context) {
	rn, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效ID"})
		return
	}
	if !requirePublicDetailAccess(c, "molecular_info", rn) {
		return
	}
	detail, err := h.svc.GetByRecordNumber(rn)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "未找到该化合物"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": detail})
}

// Create godoc
// @Summary      创建化合物
// @Description  管理员新增化合物记录
// @Tags         compounds
// @Accept       json
// @Produce      json
// @Param        compound  body      model.MolecularInfo  true  "化合物信息"
// @Success      201  {object}  object{data=model.MolecularInfo}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/compounds [post]
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

// Update godoc
// @Summary      更新化合物
// @Description  管理员更新现有化合物记录
// @Tags         compounds
// @Accept       json
// @Produce      json
// @Param        id        path      int                  true  "Record Number"
// @Param        compound  body      model.MolecularInfo  true  "化合物信息"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/compounds/{id} [put]
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

// Delete godoc
// @Summary      删除化合物
// @Description  管理员删除指定化合物记录
// @Tags         compounds
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "Record Number"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/compounds/{id} [delete]
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
