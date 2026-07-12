package middleware

import (
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

func RequestLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		query := c.Request.URL.RawQuery

		c.Next()

		cost := time.Since(start)
		status := c.Writer.Status()
		method := c.Request.Method
		clientIP := c.ClientIP()

		if query != "" {
			path = path + "?" + query
		}

		logger := zap.L().With(
			zap.Int("status", status),
			zap.String("method", method),
			zap.String("path", path),
			zap.String("ip", clientIP),
			zap.Duration("latency", cost),
		)

		if status >= 500 {
			logger.Error("server error")
		} else if status >= 400 {
			logger.Warn("client error")
		} else {
			logger.Info("request handled")
		}
	}
}
