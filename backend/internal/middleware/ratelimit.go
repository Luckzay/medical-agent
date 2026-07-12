package middleware

import (
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"golang.org/x/time/rate"
)

type ipLimiter struct {
	limiter  *rate.Limiter
	lastSeen time.Time
}

var (
	limiterMap = make(map[string]*ipLimiter)
	mu         sync.Mutex
	cleanupInterval = time.Minute
	rateLimit   = 100
	rateBurst   = 200
)

func init() {
	go cleanupLimiterMap()
}

func cleanupLimiterMap() {
	for {
		time.Sleep(cleanupInterval)
		mu.Lock()
		for ip, v := range limiterMap {
			if time.Since(v.lastSeen) > 3*time.Minute {
				delete(limiterMap, ip)
			}
		}
		mu.Unlock()
	}
}

func getLimiter(ip string) *rate.Limiter {
	mu.Lock()
	defer mu.Unlock()

	v, exists := limiterMap[ip]
	if !exists {
		limiter := rate.NewLimiter(rate.Limit(rateLimit), rateBurst)
		limiterMap[ip] = &ipLimiter{limiter: limiter, lastSeen: time.Now()}
		return limiter
	}

	v.lastSeen = time.Now()
	return v.limiter
}

func RateLimit() gin.HandlerFunc {
	return func(c *gin.Context) {
		ip := c.ClientIP()
		limiter := getLimiter(ip)

		if !limiter.Allow() {
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error": "请求过于频繁，请稍后再试",
			})
			return
		}

		c.Next()
	}
}
