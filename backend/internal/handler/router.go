package handler

import (
	"medicalagent/internal/middleware"

	"github.com/gin-gonic/gin"
)

func SetupRouter() *gin.Engine {
	r := gin.Default()

	// public
	auth := r.Group("/api/auth")
	{
		auth.POST("/login", NewUserHandler().Login)
		auth.POST("/register", NewUserHandler().Register)
	}

	// public read APIs (no auth required for browsing)
	api := r.Group("/api")

	herbs := api.Group("/herbs")
	{
		herbs.GET("", NewHerbHandler().List)
		herbs.GET("/:id", NewHerbHandler().Detail)
	}

	decoctions := api.Group("/decoctions")
	{
		decoctions.GET("", NewDecoctionHandler().List)
		decoctions.GET("/:id", NewDecoctionHandler().Detail)
	}

	couplets := api.Group("/couplets")
	{
		couplets.GET("", NewCoupletHandler().List)
		couplets.GET("/:id", NewCoupletHandler().Detail)
	}

	compounds := api.Group("/compounds")
	{
		compounds.GET("", NewCompoundHandler().List)
		compounds.GET("/:id", NewCompoundHandler().Detail)
	}

	expertises := api.Group("/expertises")
	{
		expertises.GET("", NewExpertiseHandler().List)
		expertises.GET("/:id", NewExpertiseHandler().Detail)
	}

	papers := api.Group("/papers")
	{
		papers.GET("", NewPaperHandler().List)
		papers.GET("/:id", NewPaperHandler().Detail)
	}

	// user management (requires auth + admin)
	users := api.Group("/users")
	users.Use(middleware.AuthRequired())
	{
		users.GET("", NewUserHandler().List)
		users.POST("", middleware.AdminRequired(), NewUserHandler().Create)
		users.PUT("/:id", middleware.AdminRequired(), NewUserHandler().Update)
		users.DELETE("/:id", middleware.AdminRequired(), NewUserHandler().Delete)
	}

	return r
}
