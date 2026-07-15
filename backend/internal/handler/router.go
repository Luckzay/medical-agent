package handler

import (
	_ "medicalagent/docs"
	"medicalagent/internal/middleware"

	"github.com/gin-gonic/gin"
	swaggerfiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
)

// @BasePath /api
func SetupRouter() *gin.Engine {
	r := gin.New()
	r.Use(middleware.Recovery())
	r.Use(middleware.RequestLogger())
	r.Use(middleware.RateLimit())
	r.Use(middleware.CORS())

	r.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerfiles.Handler))

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
		herbs.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewHerbHandler().Create)
		herbs.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewHerbHandler().Update)
		herbs.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewHerbHandler().Delete)
	}

	decoctions := api.Group("/decoctions")
	{
		decoctions.GET("", NewDecoctionHandler().List)
		decoctions.GET("/:id", NewDecoctionHandler().Detail)
		decoctions.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewDecoctionHandler().Create)
		decoctions.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewDecoctionHandler().Update)
		decoctions.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewDecoctionHandler().Delete)
	}

	couplets := api.Group("/couplets")
	{
		couplets.GET("", NewCoupletHandler().List)
		couplets.GET("/:id", NewCoupletHandler().Detail)
		couplets.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewCoupletHandler().Create)
		couplets.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewCoupletHandler().Update)
		couplets.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewCoupletHandler().Delete)
	}

	compounds := api.Group("/compounds")
	{
		compounds.GET("", NewCompoundHandler().List)
		compounds.GET("/:id", NewCompoundHandler().Detail)
		compounds.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewCompoundHandler().Create)
		compounds.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewCompoundHandler().Update)
		compounds.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewCompoundHandler().Delete)
	}

	expertises := api.Group("/expertises")
	{
		expertises.GET("", NewExpertiseHandler().List)
		expertises.GET("/:id", NewExpertiseHandler().Detail)
		expertises.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewExpertiseHandler().Create)
		expertises.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewExpertiseHandler().Update)
		expertises.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewExpertiseHandler().Delete)
	}

	papers := api.Group("/papers")
	{
		papers.GET("", NewPaperHandler().List)
		papers.GET("/:id", NewPaperHandler().Detail)
		papers.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewPaperHandler().Create)
		papers.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewPaperHandler().Update)
		papers.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewPaperHandler().Delete)
	}

	// user management (requires auth + admin)
	users := api.Group("/users")
	users.Use(middleware.AuthRequired())
	{
		users.GET("", middleware.AdminRequired(), NewUserHandler().List)
		users.POST("", middleware.AdminRequired(), NewUserHandler().Create)
		users.PUT("/:id", middleware.AdminRequired(), NewUserHandler().Update)
		users.DELETE("/:id", middleware.AdminRequired(), NewUserHandler().Delete)
	}

	return r
}
