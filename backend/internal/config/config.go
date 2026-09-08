package config

import (
	"github.com/spf13/viper"
	"go.uber.org/zap"
)

type Config struct {
	DB               DBConfig
	Redis            RedisConfig
	RocketMQ         RocketMQConfig
	JWT              JWTConfig
	Server           ServerConfig
	Agent            AgentConfig
	LLMEncryptionKey string
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

type RocketMQConfig struct {
	NameServerAddr string
	Topic          string
	ConsumerGroup  string
}

type JWTConfig struct {
	Secret string
}

type ServerConfig struct {
	Port              string
	CORSAllowedOrigin string
}

type AgentConfig struct {
	ServiceURL     string
	TimeoutSeconds int
	InternalToken  string
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
		RocketMQ: RocketMQConfig{
			NameServerAddr: viper.GetString("ROCKETMQ_NAMESRV_ADDR"),
			Topic:          viper.GetString("ROCKETMQ_TOPIC"),
			ConsumerGroup:  viper.GetString("ROCKETMQ_CONSUMER_GROUP"),
		},
		JWT: JWTConfig{
			Secret: viper.GetString("JWT_SECRET"),
		},
		Server: ServerConfig{
			Port:              viper.GetString("SERVER_PORT"),
			CORSAllowedOrigin: viper.GetString("CORS_ALLOWED_ORIGIN"),
		},
		Agent: AgentConfig{
			ServiceURL:     viper.GetString("AGENT_SERVICE_URL"),
			TimeoutSeconds: viper.GetInt("AGENT_SERVICE_TIMEOUT_SECONDS"),
			InternalToken:  viper.GetString("AGENT_INTERNAL_TOKEN"),
		},
		LLMEncryptionKey: viper.GetString("LLM_ENCRYPTION_KEY"),
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
	if cfg.RocketMQ.NameServerAddr == "" {
		cfg.RocketMQ.NameServerAddr = "127.0.0.1:9876"
	}
	if cfg.RocketMQ.Topic == "" {
		cfg.RocketMQ.Topic = "medical-agent-runs"
	}
	if cfg.RocketMQ.ConsumerGroup == "" {
		cfg.RocketMQ.ConsumerGroup = "medical-agent-workers"
	}
	if cfg.Agent.ServiceURL == "" {
		cfg.Agent.ServiceURL = "http://127.0.0.1:8090"
	}
	if cfg.Agent.TimeoutSeconds <= 0 {
		cfg.Agent.TimeoutSeconds = 10
	}

	return cfg
}
