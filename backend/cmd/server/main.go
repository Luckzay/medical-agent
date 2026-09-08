package main

import (
	"fmt"
	"strings"
	_ "time/tzdata"

	"medicalagent/internal/cache"
	"medicalagent/internal/config"
	"medicalagent/internal/handler"
	"medicalagent/internal/middleware"
	"medicalagent/internal/repository"

	"go.uber.org/zap"
)

// @title           AI Medical Agent API
// @version         1.0
// @description     中医药知识库 API 服务 —— 方剂、单味药、对药、论文、分子信息、名家经验管理
// @termsOfService    http://swagger.io/terms/

// @contact.name   API Support
// @contact.url    http://www.swagger.io/support
// @contact.email  support@swagger.io

// @license.name  Apache 2.0
// @license.url   http://www.apache.org/licenses/LICENSE-2.0.html

// @host      localhost:8080
// @BasePath  /api

// @securityDefinitions.apikey BearerAuth
// @in header
// @name Authorization
func main() {
	logger, _ := zap.NewProduction()
	defer logger.Sync()
	zap.ReplaceGlobals(logger)

	cfg := config.Load()
	if strings.TrimSpace(cfg.JWT.Secret) == "" {
		zap.L().Fatal("JWT_SECRET is required")
	}
	cfg.Agent.InternalToken = strings.TrimSpace(cfg.Agent.InternalToken)
	if cfg.Agent.InternalToken == "" {
		zap.L().Fatal("AGENT_INTERNAL_TOKEN is required")
	}

	middleware.JWTSecret = cfg.JWT.Secret
	middleware.CORSAllowedOrigin = cfg.Server.CORSAllowedOrigin

	if err := repository.InitDB(cfg.DB); err != nil {
		zap.L().Fatal("Failed to connect to database", zap.Error(err))
	}
	zap.L().Info("Database connected successfully")

	cache.Init(cfg.Redis)

	r := handler.SetupRouter(cfg)

	addr := fmt.Sprintf(":%s", cfg.Server.Port)
	zap.L().Info("Server starting", zap.String("addr", addr))
	if err := r.Run(addr); err != nil {
		zap.L().Fatal("Failed to start server", zap.Error(err))
	}
}
