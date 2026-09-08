package handler

import (
	"time"

	_ "medicalagent/docs"
	agentclient "medicalagent/internal/client/agent"
	"medicalagent/internal/config"
	"medicalagent/internal/middleware"
	"medicalagent/internal/repository"
	"medicalagent/internal/service"

	"github.com/gin-gonic/gin"
	swaggerfiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
)

// @BasePath /api
func SetupRouter(cfg *config.Config) *gin.Engine {
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

	// Public reads accept an optional JWT. Protected routes below additionally
	// require it, while guest reads are constrained by the handlers.
	api := r.Group("/api")
	api.Use(middleware.OptionalAuth())

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

	casesHandler := NewImportedContentHandler("case")
	cases := api.Group("/cases")
	{
		cases.GET("", casesHandler.List)
		cases.GET("/:id", casesHandler.Detail)
	}

	clausesHandler := NewImportedContentHandler("clause")
	clauses := api.Group("/clauses")
	{
		clauses.GET("", clausesHandler.List)
		clauses.GET("/:id", clausesHandler.Detail)
	}

	papers := api.Group("/papers")
	{
		papers.GET("", NewPaperHandler().List)
		papers.GET("/:id", NewPaperHandler().Detail)
		papers.POST("", middleware.AuthRequired(), middleware.AdminRequired(), NewPaperHandler().Create)
		papers.PUT("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewPaperHandler().Update)
		papers.DELETE("/:id", middleware.AuthRequired(), middleware.AdminRequired(), NewPaperHandler().Delete)
	}

	agentHTTPClient := agentclient.NewHTTPClient(cfg.Agent.ServiceURL, cfg.Agent.InternalToken, time.Duration(cfg.Agent.TimeoutSeconds)*time.Second)
	agentRunHandler := NewAgentRunHandler(service.NewAgentRunService(repository.NewAgentRunRepo(), agentHTTPClient))
	agentRuns := api.Group("/agent/runs")
	agentRuns.Use(middleware.AuthRequired())
	{
		agentRuns.POST("", agentRunHandler.Create)
		agentRuns.GET("/:run_id", agentRunHandler.Get)
		agentRuns.POST("/:run_id/resume", agentRunHandler.Resume)
	}

	agentChatHandler := NewAgentChatHandler(service.NewAgentChatService(repository.NewAgentChatRepo(), agentHTTPClient))
	agentSessions := api.Group("/agent/sessions")
	agentSessions.Use(middleware.AuthRequired())
	{
		agentSessions.POST("", agentChatHandler.CreateSession)
		agentSessions.GET("", agentChatHandler.ListSessions)
		agentSessions.GET("/:id", agentChatHandler.GetSession)
		agentSessions.POST("/:id/messages", agentChatHandler.SendMessage)
		agentSessions.GET("/:id/turns/:turn_id", agentChatHandler.GetTurn)
		agentSessions.GET("/:id/turns/:turn_id/stream", agentChatHandler.StreamTurn)
	}

	// user management (requires auth + admin)
	users := api.Group("/users")
	users.Use(middleware.AuthRequired())
	{
		users.GET("", middleware.AdminRequired(), NewUserHandler().List)
		users.POST("", middleware.AdminRequired(), NewUserHandler().Create)
		users.PUT("/:id", middleware.AdminRequired(), NewUserHandler().Update)
		users.PATCH("/:id/status", middleware.AdminRequired(), NewUserHandler().UpdateStatus)
		users.DELETE("/:id", middleware.AdminRequired(), NewUserHandler().Delete)
	}

	llmConfigSvc := service.NewLLMConfigService(repository.NewLLMConfigRepo(), cfg.LLMEncryptionKey, cfg.Agent.InternalToken)
	llmConfigHandler := NewLLMConfigHandler(llmConfigSvc)

	adminLLM := api.Group("/admin/llm-config")
	adminLLM.Use(middleware.AuthRequired(), middleware.AdminRequired())
	{
		adminLLM.GET("", llmConfigHandler.Get)
		adminLLM.PUT("", llmConfigHandler.Update)
	}

	internal := r.Group("/internal/v1/llm")
	{
		internal.POST("/chat", llmConfigHandler.InternalChat)
		internal.POST("/chat/stream", llmConfigHandler.InternalChatStream)
	}

	knowledgeHandler := NewKnowledgeHandler(service.NewKnowledgeService(repository.NewKnowledgeRepo()), cfg.Agent.InternalToken)
	r.POST("/internal/v1/knowledge/search", knowledgeHandler.Search)

	return r
}
