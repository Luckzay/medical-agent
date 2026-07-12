package cache

import (
	"context"
	"encoding/json"
	"time"

	"medicalagent/internal/config"

	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

var Client *redis.Client
var enabled bool

func Init(cfg config.RedisConfig) {
	if cfg.Addr == "" {
		zap.L().Warn("Redis address not configured, cache disabled")
		enabled = false
		return
	}

	Client = redis.NewClient(&redis.Options{
		Addr:     cfg.Addr,
		Password: cfg.Password,
		DB:       0,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	if err := Client.Ping(ctx).Err(); err != nil {
		zap.L().Warn("Failed to connect to Redis, cache disabled", zap.Error(err))
		enabled = false
		Client = nil
		return
	}

	enabled = true
	zap.L().Info("Redis connected successfully", zap.String("addr", cfg.Addr))
}

func IsEnabled() bool {
	return enabled && Client != nil
}

func Get(ctx context.Context, key string, dest any) bool {
	if !IsEnabled() {
		return false
	}
	data, err := Client.Get(ctx, key).Bytes()
	if err != nil {
		return false
	}
	if err := json.Unmarshal(data, dest); err != nil {
		zap.L().Warn("cache unmarshal failed", zap.String("key", key), zap.Error(err))
		return false
	}
	return true
}

func Set(ctx context.Context, key string, value any, ttl time.Duration) {
	if !IsEnabled() {
		return
	}
	data, err := json.Marshal(value)
	if err != nil {
		zap.L().Warn("cache marshal failed", zap.String("key", key), zap.Error(err))
		return
	}
	if err := Client.Set(ctx, key, data, ttl).Err(); err != nil {
		zap.L().Warn("cache set failed", zap.String("key", key), zap.Error(err))
	}
}

func Del(ctx context.Context, keys ...string) {
	if !IsEnabled() {
		return
	}
	if err := Client.Del(ctx, keys...).Err(); err != nil {
		zap.L().Warn("cache del failed", zap.Strings("keys", keys), zap.Error(err))
	}
}

func DelPattern(ctx context.Context, pattern string) {
	if !IsEnabled() {
		return
	}
	var cursor uint64
	for {
		keys, next, err := Client.Scan(ctx, cursor, pattern, 100).Result()
		if err != nil {
			zap.L().Warn("cache scan failed", zap.String("pattern", pattern), zap.Error(err))
			return
		}
		if len(keys) > 0 {
			Del(ctx, keys...)
		}
		cursor = next
		if cursor == 0 {
			break
		}
	}
}
