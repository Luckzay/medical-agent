package main

import (
	"fmt"

	"medicalagent/internal/config"
	"medicalagent/internal/handler"
	"medicalagent/internal/middleware"
	"medicalagent/internal/repository"

	"go.uber.org/zap"
)

func main() {
	logger, _ := zap.NewProduction()
	defer logger.Sync()
	zap.ReplaceGlobals(logger)

	cfg := config.Load()

	middleware.JWTSecret = cfg.JWT.Secret

	if err := repository.InitDB(cfg.DB); err != nil {
		zap.L().Fatal("Failed to connect to database", zap.Error(err))
	}
	zap.L().Info("Database connected successfully")

	r := handler.SetupRouter()
	r.Use(middleware.CORS())

	addr := fmt.Sprintf(":%s", cfg.Server.Port)
	zap.L().Info("Server starting", zap.String("addr", addr))
	if err := r.Run(addr); err != nil {
		zap.L().Fatal("Failed to start server", zap.Error(err))
	}
}
