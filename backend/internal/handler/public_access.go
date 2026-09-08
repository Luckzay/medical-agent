package handler

import (
	"net/http"
	"strconv"

	"medicalagent/internal/repository"

	"github.com/gin-gonic/gin"
)

const guestPageLimit = 20

func isAuthenticated(c *gin.Context) bool {
	authenticated, _ := c.Get("authenticated")
	return authenticated == true
}

// publicPagination centralizes the guest data boundary. Signed-in users retain
// normal pagination; guests always receive the first page with at most 20 rows.
func publicPagination(c *gin.Context) (page, pageSize int, guest bool) {
	page, _ = strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ = strconv.Atoi(c.DefaultQuery("page_size", "20"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 20
	}
	guest = !isAuthenticated(c)
	if guest {
		page = 1
		if pageSize > guestPageLimit {
			pageSize = guestPageLimit
		}
	}
	return
}

func publicTotal(total int64, guest bool) int64 {
	if guest && total > guestPageLimit {
		return guestPageLimit
	}
	return total
}

func requirePublicDetailAccess(c *gin.Context, table string, id any) bool {
	if isAuthenticated(c) {
		return true
	}
	allowed, err := repository.IsPublicRecord(table, id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "检查访问范围失败"})
		return false
	}
	if !allowed {
		c.JSON(http.StatusForbidden, gin.H{"error": "游客只能访问前20条记录"})
		return false
	}
	return true
}
