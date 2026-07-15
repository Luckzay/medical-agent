package config

import (
	"github.com/spf13/viper"
	"go.uber.org/zap"
)

type Config struct {
	DB     DBConfig
	Redis  RedisConfig
	JWT    JWTConfig
	Server ServerConfig
}

type DBConfig struct {
	User     string
	Password string
	Host     string
	Port     string
	Name     string
}

type RedisConfig struct {
	Addr     string
	Password string
}

type JWTConfig struct {
	Secret string
}

type ServerConfig struct {
	Port              string
	CORSAllowedOrigin string
}

func (c DBConfig) DSN() string {
	return c.User + ":" + c.Password + "@tcp(" + c.Host + ":" + c.Port + ")/" + c.Name +
		"?charset=utf8mb4&parseTime=true&loc=Asia%2FShanghai"
}

func Load() *Config {
	viper.SetConfigFile(".env")
	viper.AutomaticEnv()
	if err := viper.ReadInConfig(); err != nil {
		zap.L().Warn("No .env file found, using env vars only", zap.Error(err))
	}

	cfg := &Config{
		DB: DBConfig{
			User:     viper.GetString("DB_USER"),
			Password: viper.GetString("DB_PASSWORD"),
			Host:     viper.GetString("DB_HOST"),
			Port:     viper.GetString("DB_PORT"),
			Name:     viper.GetString("DB_NAME"),
		},
		Redis: RedisConfig{
			Addr:     viper.GetString("REDIS_ADDR"),
			Password: viper.GetString("REDIS_PASSWORD"),
		},
		JWT: JWTConfig{
			Secret: viper.GetString("JWT_SECRET"),
		},
		Server: ServerConfig{
			Port:              viper.GetString("SERVER_PORT"),
			CORSAllowedOrigin: viper.GetString("CORS_ALLOWED_ORIGIN"),
		},
	}

	if cfg.Server.Port == "" {
		cfg.Server.Port = "8080"
	}
	if cfg.DB.Port == "" {
		cfg.DB.Port = "3306"
	}
	if cfg.DB.Host == "" {
		cfg.DB.Host = "127.0.0.1"
	}
	if cfg.Server.CORSAllowedOrigin == "" {
		cfg.Server.CORSAllowedOrigin = "http://localhost:3000"
	}

	return cfg
}
