package handler

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"medicalagent/internal/middleware"
	"medicalagent/internal/model"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

type UserHandler struct {
	svc *service.UserService
}

type LoginRequest struct {
	Username string `json:"username" binding:"required" example:"admin"`
	Password string `json:"password" binding:"required" example:"123456"`
}

type UpdateUserStatusRequest struct {
	Status string `json:"status" binding:"required" example:"active"`
}

func NewUserHandler() *UserHandler { return &UserHandler{svc: service.NewUserService()} }

func validateRequiredUserProfile(user *model.User) string {
	user.Affiliation = strings.TrimSpace(user.Affiliation)
	user.ProfessionalTitle = strings.TrimSpace(user.ProfessionalTitle)
	if user.Affiliation == "" {
		return "单位不能为空"
	}
	if user.ProfessionalTitle == "" {
		return "职称不能为空"
	}
	return ""
}

func prepareRegistration(user *model.User) {
	user.Role = "user"
	user.Status = model.UserStatusPending
}

func prepareAdminCreatedUser(user *model.User) {
	if user.Role == "" {
		user.Role = "user"
	}
	user.Status = model.UserStatusActive
}

// Login godoc
// @Summary      用户登录
// @Description  使用用户名和密码登录，返回 JWT token
// @Tags         auth
// @Accept       json
// @Produce      json
// @Param        request  body      LoginRequest  true  "登录信息"
// @Success      200  {object}  object{token=string,user=model.UserResponse}
// @Failure      400  {object}  object{error=string}
// @Failure      401  {object}  object{error=string}
// @Router       /api/auth/login [post]
func (h *UserHandler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请输入用户名和密码"})
		return
	}
	userResp, err := h.svc.Login(req.Username, req.Password)
	zap.L().Info("login", zap.String("username", req.Username))
	if err != nil {
		switch {
		case errors.Is(err, service.ErrUserPending), errors.Is(err, service.ErrUserRejected):
			c.JSON(http.StatusForbidden, gin.H{"error": err.Error()})
		default:
			c.JSON(http.StatusUnauthorized, gin.H{"error": "用户名或密码错误"})
		}
		zap.L().Error("login", zap.Error(err))
		return
	}
	token, err := middleware.GenerateToken(userResp.ID, userResp.Username, userResp.Role)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "生成令牌失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token, "user": userResp})
}

// Register godoc
// @Summary      用户注册
// @Description  新用户申请注册，初始状态为 pending
// @Tags         auth
// @Accept       json
// @Produce      json
// @Param        user  body      model.User  true  "用户信息"
// @Success      201  {object}  object{data=model.UserResponse}
// @Failure      400  {object}  object{error=string}
// @Failure      409  {object}  object{error=string}
// @Router       /api/auth/register [post]
func (h *UserHandler) Register(c *gin.Context) {
	var user model.User
	if err := c.ShouldBindJSON(&user); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	zap.L().Info("register", zap.Any("user", user.Username))
	if user.Username == "" || user.Password == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "用户名和密码不能为空"})
		return
	}
	if message := validateRequiredUserProfile(&user); message != "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": message})
		return
	}
	prepareRegistration(&user)
	userResp, err := h.svc.Create(&user)
	if err != nil {
		c.JSON(http.StatusConflict, gin.H{"error": "注册失败，用户名或邮箱可能已存在"})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"data": userResp})
}

// List godoc
// @Summary      获取用户列表
// @Description  管理员分页查看所有用户信息
// @Tags         users
// @Accept       json
// @Produce      json
// @Param        page       query      int  false  "页码"      default(1)
// @Param        page_size  query      int  false  "每页数量"   default(20)
// @Success      200  {object}  object{data=[]model.UserResponse,total=int64,page=int,page_size=int}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/users [get]
func (h *UserHandler) List(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 20
	}

	list, total, err := h.svc.List(page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": list, "total": total, "page": page, "page_size": pageSize})
}

// Create godoc
// @Summary      管理员创建用户
// @Description  管理员直接创建已激活状态的用户
// @Tags         users
// @Accept       json
// @Produce      json
// @Param        user  body      model.User  true  "用户信息"
// @Success      201  {object}  object{data=model.UserResponse}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/users [post]
func (h *UserHandler) Create(c *gin.Context) {
	var user model.User
	if err := c.ShouldBindJSON(&user); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if message := validateRequiredUserProfile(&user); message != "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": message})
		return
	}
	prepareAdminCreatedUser(&user)
	userResp, err := h.svc.Create(&user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"data": userResp})
}

// Update godoc
// @Summary      更新用户信息
// @Description  管理员更新指定用户的信息
// @Tags         users
// @Accept       json
// @Produce      json
// @Param        id    path      int         true  "用户 ID"
// @Param        user  body      model.User  true  "用户信息"
// @Success      200   {object}  object{message=string}
// @Failure      400   {object}  object{error=string}
// @Failure      500   {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/users/{id} [put]
func (h *UserHandler) Update(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的用户ID"})
		return
	}
	var user model.User
	if err := c.ShouldBindJSON(&user); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	user.ID = id
	if err := h.svc.Update(&user); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "更新成功"})
}

// UpdateStatus godoc
// @Summary      审核用户状态
// @Description  管理员审核用户注册申请，更新状态（如 active, rejected）
// @Tags         users
// @Accept       json
// @Produce      json
// @Param        id       path      int                      true  "用户 ID"
// @Param        request  body      UpdateUserStatusRequest  true  "状态信息"
// @Success      200  {object}  object{message=string,status=string}
// @Failure      400  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/users/{id}/status [patch]
func (h *UserHandler) UpdateStatus(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil || id < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的用户ID"})
		return
	}
	var req UpdateUserStatusRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请输入用户状态"})
		return
	}
	role, _ := c.Get("role")
	if err := h.svc.UpdateStatus(id, req.Status, role == "admin"); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "审核状态更新成功", "status": req.Status})
}

// Delete godoc
// @Summary      删除用户
// @Description  管理员删除指定用户
// @Tags         users
// @Accept       json
// @Produce      json
// @Param        id   path      int  true  "用户 ID"
// @Success      200  {object}  object{message=string}
// @Failure      400  {object}  object{error=string}
// @Failure      500  {object}  object{error=string}
// @Security     BearerAuth
// @Router       /api/users/{id} [delete]
func (h *UserHandler) Delete(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无效的用户ID"})
		return
	}
	if err := h.svc.Delete(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "删除成功"})
}
