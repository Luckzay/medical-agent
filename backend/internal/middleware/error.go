package middleware

import (
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"gorm.io/gorm"
)

type AppError struct {
	Code    int
	Message string
	Err     error
}

func (e *AppError) Error() string {
	if e.Err != nil {
		return e.Message + ": " + e.Err.Error()
	}
	return e.Message
}

func NewAppError(code int, message string, err error) *AppError {
	return &AppError{Code: code, Message: message, Err: err}
}

func Recovery() gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			if err := recover(); err != nil {
				zap.L().Error("panic recovered", zap.Any("error", err))
				c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
					"error": "服务器内部错误",
				})
			}
		}()
		c.Next()
	}
}

func WrapError(err error, defaultMsg string) (int, string) {
	if err == nil {
		return http.StatusOK, ""
	}

	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code, appErr.Message
	}

	if errors.Is(err, gorm.ErrRecordNotFound) {
		return http.StatusNotFound, "资源不存在"
	}

	zap.L().Warn("unhandled error", zap.Error(err))
	return http.StatusInternalServerError, defaultMsg
}
