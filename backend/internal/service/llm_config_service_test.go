package service

import (
	"context"
	"medicalagent/internal/model"
	"testing"
)

type mockLLMConfigRepo struct {
	cfg *model.LLMConfig
}

func (m *mockLLMConfigRepo) Get(ctx context.Context) (*model.LLMConfig, error) {
	if m.cfg == nil {
		return nil, nil
	}
	return m.cfg, nil
}

func (m *mockLLMConfigRepo) Save(ctx context.Context, cfg *model.LLMConfig) error {
	m.cfg = cfg
	return nil
}

func TestLLMConfigService(t *testing.T) {
	masterKey := "12345678901234567890123456789012"
	internalToken := "test-token"
	repo := &mockLLMConfigRepo{}
	svc := NewLLMConfigService(repo, masterKey, internalToken)

	ctx := context.Background()

	// Test Update
	input := model.LLMConfig{
		Provider:  "openai",
		BaseURL:   "https://api.openai.com/v1",
		ModelName: "gpt-4",
		Enabled:   true,
	}
	err := svc.UpdateConfig(ctx, input, "sk-test-key")
	if err != nil {
		t.Fatalf("UpdateConfig failed: %v", err)
	}

	// Test Get
	resp, err := svc.GetConfig(ctx)
	if err != nil {
		t.Fatalf("GetConfig failed: %v", err)
	}
	if resp.Provider != "openai" || !resp.HasAPIKey || resp.MaskedAPIKey != "sk-****" {
		t.Errorf("Unexpected GetConfig response: %+v", resp)
	}

	// Test Verify Token
	if !svc.VerifyInternalToken("test-token") {
		t.Error("VerifyInternalToken failed")
	}
}
