package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"medicalagent/internal/model"
	"medicalagent/internal/repository"
	"medicalagent/internal/util"

	"gorm.io/gorm"
)

const (
	MaxLLMMessages        = 50
	MaxLLMTools           = 32
	MaxLLMContentBytes    = 65536
	MaxLLMRequestBodySize = 256 << 10
)

var (
	ErrLLMNotConfigured  = errors.New("LLM is not configured or disabled")
	ErrInvalidMasterKey  = errors.New("invalid or missing LLM_ENCRYPTION_KEY")
	ErrInvalidLLMRequest = errors.New("invalid LLM chat request")
)

type LLMChatMessage struct {
	Role       string            `json:"role"`
	Content    string            `json:"content"`
	ToolCallID string            `json:"tool_call_id,omitempty"`
	ToolCalls  []json.RawMessage `json:"tool_calls,omitempty"`
}

type LLMChatRequest struct {
	Messages   []LLMChatMessage  `json:"messages"`
	Tools      []json.RawMessage `json:"tools,omitempty"`
	ToolChoice string            `json:"tool_choice,omitempty"`
}

type LLMChatResponse struct {
	Content   string            `json:"content"`
	Model     string            `json:"model"`
	Provider  string            `json:"provider"`
	ToolCalls []json.RawMessage `json:"tool_calls,omitempty"`
}

type LLMConfigService interface {
	GetConfig(ctx context.Context) (model.LLMConfigResponse, error)
	UpdateConfig(ctx context.Context, input model.LLMConfig, plainKey string) error
	Chat(ctx context.Context, systemPrompt, userPrompt string) (map[string]any, error)
	VerifyInternalToken(token string) bool
}

type llmConfigService struct {
	repo          repository.LLMConfigRepository
	masterKey     []byte
	httpClient    *http.Client
	internalToken string
}

func NewLLMConfigService(repo repository.LLMConfigRepository, masterKeyStr string, internalToken string) LLMConfigService {
	key, _ := util.ParseMasterKey(masterKeyStr)
	return &llmConfigService{repo: repo, masterKey: key, httpClient: &http.Client{Timeout: 60 * time.Second}, internalToken: internalToken}
}

func (s *llmConfigService) GetConfig(ctx context.Context) (model.LLMConfigResponse, error) {
	cfg, err := s.repo.Get(ctx)
	if err != nil {
		return model.LLMConfigResponse{}, err
	}
	hasKey := cfg.APIKeyEncrypted != ""
	maskedKey := ""
	if hasKey {
		maskedKey = "sk-****"
	}
	return model.LLMConfigResponse{Provider: cfg.Provider, BaseURL: cfg.BaseURL, ModelName: cfg.ModelName, Enabled: cfg.Enabled, HasAPIKey: hasKey, MaskedAPIKey: maskedKey, UpdatedBy: cfg.UpdatedBy, UpdatedAt: cfg.UpdatedAt}, nil
}

func (s *llmConfigService) UpdateConfig(ctx context.Context, input model.LLMConfig, plainKey string) error {
	if len(s.masterKey) == 0 {
		return ErrInvalidMasterKey
	}
	input.Provider = strings.TrimSpace(input.Provider)
	input.BaseURL = strings.TrimRight(strings.TrimSpace(input.BaseURL), "/")
	input.ModelName = strings.TrimSpace(input.ModelName)
	if input.Provider == "" || input.ModelName == "" {
		return errors.New("provider and model_name are required")
	}
	if !isValidURL(input.BaseURL) {
		return errors.New("invalid base_url: must be an absolute http or https URL")
	}
	existing, err := s.repo.Get(ctx)
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return fmt.Errorf("load llm config: %w", err)
	}
	if errors.Is(err, gorm.ErrRecordNotFound) {
		existing = nil
	}
	if plainKey != "" {
		encrypted, err := util.Encrypt(plainKey, s.masterKey)
		if err != nil {
			return fmt.Errorf("encrypt api key: %w", err)
		}
		input.APIKeyEncrypted = encrypted
	} else if existing != nil {
		input.APIKeyEncrypted = existing.APIKeyEncrypted
	}
	if input.APIKeyEncrypted == "" {
		return errors.New("api_key is required for new configuration")
	}
	return s.repo.Save(ctx, &input)
}

func (s *llmConfigService) Chat(ctx context.Context, systemPrompt, userPrompt string) (map[string]any, error) {
	if len(systemPrompt)+len(userPrompt) > 20000 {
		return nil, ErrInvalidLLMRequest
	}
	response, err := s.ChatMessages(ctx, LLMChatRequest{Messages: []LLMChatMessage{{Role: "system", Content: systemPrompt}, {Role: "user", Content: userPrompt}}})
	if err != nil {
		return nil, err
	}
	result := map[string]any{"content": response.Content, "model": response.Model, "provider": response.Provider}
	if len(response.ToolCalls) > 0 {
		result["tool_calls"] = response.ToolCalls
	}
	return result, nil
}

func (s *llmConfigService) ChatMessages(ctx context.Context, input LLMChatRequest) (LLMChatResponse, error) {
	if err := validateLLMChatRequest(input); err != nil {
		return LLMChatResponse{}, err
	}
	if len(s.masterKey) == 0 {
		return LLMChatResponse{}, ErrInvalidMasterKey
	}
	cfg, err := s.repo.Get(ctx)
	if err != nil || !cfg.Enabled {
		return LLMChatResponse{}, ErrLLMNotConfigured
	}
	apiKey, err := util.Decrypt(cfg.APIKeyEncrypted, s.masterKey)
	if err != nil {
		return LLMChatResponse{}, fmt.Errorf("decrypt api key: %w", err)
	}
	payload := struct {
		Model      string            `json:"model"`
		Messages   []LLMChatMessage  `json:"messages"`
		Tools      []json.RawMessage `json:"tools,omitempty"`
		ToolChoice string            `json:"tool_choice,omitempty"`
	}{Model: cfg.ModelName, Messages: input.Messages, Tools: input.Tools, ToolChoice: input.ToolChoice}
	body, err := json.Marshal(payload)
	if err != nil {
		return LLMChatResponse{}, ErrInvalidLLMRequest
	}
	if len(body) > MaxLLMRequestBodySize {
		return LLMChatResponse{}, ErrInvalidLLMRequest
	}
	apiURL := strings.TrimRight(cfg.BaseURL, "/") + "/chat/completions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, apiURL, bytes.NewReader(body))
	if err != nil {
		return LLMChatResponse{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return LLMChatResponse{}, fmt.Errorf("llm api call failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
		return LLMChatResponse{}, fmt.Errorf("llm api returned status %d", resp.StatusCode)
	}
	var result struct {
		Model   string `json:"model"`
		Choices []struct {
			Message struct {
				Content   string            `json:"content"`
				ToolCalls []json.RawMessage `json:"tool_calls"`
			} `json:"message"`
		} `json:"choices"`
	}
	decoder := json.NewDecoder(io.LimitReader(resp.Body, MaxLLMRequestBodySize+1))
	if err := decoder.Decode(&result); err != nil {
		return LLMChatResponse{}, errors.New("invalid response from llm api")
	}
	if len(result.Choices) == 0 || len(result.Choices[0].Message.ToolCalls) > MaxLLMTools {
		return LLMChatResponse{}, errors.New("invalid response from llm api")
	}
	modelName := result.Model
	if modelName == "" {
		modelName = cfg.ModelName
	}
	return LLMChatResponse{Content: result.Choices[0].Message.Content, Model: modelName, Provider: cfg.Provider, ToolCalls: result.Choices[0].Message.ToolCalls}, nil
}

func validateLLMChatRequest(input LLMChatRequest) error {
	if len(input.Messages) == 0 || len(input.Messages) > MaxLLMMessages || len(input.Tools) > MaxLLMTools {
		return ErrInvalidLLMRequest
	}
	if input.ToolChoice != "" && input.ToolChoice != "auto" && input.ToolChoice != "none" && input.ToolChoice != "required" {
		return ErrInvalidLLMRequest
	}
	total := 0
	for _, message := range input.Messages {
		switch message.Role {
		case "system", "user", "assistant", "tool":
		default:
			return ErrInvalidLLMRequest
		}
		if message.Role == "tool" && strings.TrimSpace(message.ToolCallID) == "" {
			return ErrInvalidLLMRequest
		}
		if len(message.ToolCalls) > MaxLLMTools {
			return ErrInvalidLLMRequest
		}
		total += len(message.Content) + len(message.ToolCallID)
		for _, call := range message.ToolCalls {
			if !validJSONObject(call) {
				return ErrInvalidLLMRequest
			}
			total += len(call)
		}
	}
	for _, tool := range input.Tools {
		if !validJSONObject(tool) {
			return ErrInvalidLLMRequest
		}
		total += len(tool)
	}
	if total > MaxLLMContentBytes {
		return ErrInvalidLLMRequest
	}
	return nil
}

func validJSONObject(value json.RawMessage) bool {
	trimmed := bytes.TrimSpace(value)
	return len(trimmed) >= 2 && trimmed[0] == '{' && trimmed[len(trimmed)-1] == '}' && json.Valid(trimmed)
}

func (s *llmConfigService) VerifyInternalToken(token string) bool {
	if s.internalToken == "" || token == "" {
		return false
	}
	return util.ConstantTimeCompare(token, s.internalToken)
}

func isValidURL(value string) bool {
	parsed, err := url.Parse(value)
	return err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") && parsed.Host != "" && parsed.User == nil
}
