package service

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"medicalagent/internal/util"
)

// LLMStreamEvent is a normalized event emitted by an OpenAI-compatible stream.
type LLMStreamEvent struct {
	Event string
	Data  any
}

type LLMDeltaEvent struct {
	Content string `json:"content"`
}

type LLMToolCallDeltaEvent struct {
	Index     int    `json:"index"`
	ID        string `json:"id,omitempty"`
	Name      string `json:"name,omitempty"`
	Arguments string `json:"arguments,omitempty"`
}

type LLMDoneEvent struct {
	Model    string `json:"model"`
	Provider string `json:"provider"`
}

type LLMErrorEvent struct {
	Error string `json:"error"`
}

var errLLMStreamDone = errors.New("llm stream done")

// ChatMessagesStream forwards normalized deltas as they arrive. It deliberately
// uses bufio.Reader rather than Scanner so valid SSE frames are not limited to 64 KiB.
func (s *llmConfigService) ChatMessagesStream(ctx context.Context, input LLMChatRequest, emit func(LLMStreamEvent) error) error {
	if err := validateLLMChatRequest(input); err != nil {
		return err
	}
	if len(s.masterKey) == 0 {
		return ErrInvalidMasterKey
	}
	cfg, err := s.repo.Get(ctx)
	if err != nil || !cfg.Enabled {
		return ErrLLMNotConfigured
	}
	apiKey, err := util.Decrypt(cfg.APIKeyEncrypted, s.masterKey)
	if err != nil {
		return fmt.Errorf("decrypt api key: %w", err)
	}
	payload := struct {
		Model      string            `json:"model"`
		Messages   []LLMChatMessage  `json:"messages"`
		Tools      []json.RawMessage `json:"tools,omitempty"`
		ToolChoice string            `json:"tool_choice,omitempty"`
		Stream     bool              `json:"stream"`
	}{cfg.ModelName, input.Messages, input.Tools, input.ToolChoice, true}
	body, err := json.Marshal(payload)
	if err != nil || len(body) > MaxLLMRequestBodySize {
		return ErrInvalidLLMRequest
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(cfg.BaseURL, "/")+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build llm stream request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("Authorization", "Bearer "+apiKey)
	streamClient := *s.httpClient
	streamClient.Timeout = 0 // the request context, not a whole-response timeout, owns stream lifetime
	resp, err := streamClient.Do(req)
	if err != nil {
		return fmt.Errorf("llm stream call failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("llm api returned status %d", resp.StatusCode)
	}

	modelName := cfg.ModelName
	done := false
	err = readSSEData(ctx, resp.Body, func(data []byte) error {
		if string(data) == "[DONE]" {
			done = true
			if err := emit(LLMStreamEvent{Event: "done", Data: LLMDoneEvent{Model: modelName, Provider: cfg.Provider}}); err != nil {
				return err
			}
			return errLLMStreamDone
		}
		var frame struct {
			Model   string `json:"model"`
			Choices []struct {
				Delta struct {
					Content   string `json:"content"`
					ToolCalls []struct {
						Index    int    `json:"index"`
						ID       string `json:"id"`
						Function struct {
							Name      string `json:"name"`
							Arguments string `json:"arguments"`
						} `json:"function"`
					} `json:"tool_calls"`
				} `json:"delta"`
			} `json:"choices"`
		}
		if err := json.Unmarshal(data, &frame); err != nil {
			return errors.New("invalid SSE frame from llm api")
		}
		if frame.Model != "" {
			modelName = frame.Model
		}
		for _, choice := range frame.Choices {
			if choice.Delta.Content != "" {
				if err := emit(LLMStreamEvent{Event: "delta", Data: LLMDeltaEvent{Content: choice.Delta.Content}}); err != nil {
					return err
				}
			}
			for _, call := range choice.Delta.ToolCalls {
				if err := emit(LLMStreamEvent{Event: "tool_call_delta", Data: LLMToolCallDeltaEvent{Index: call.Index, ID: call.ID, Name: call.Function.Name, Arguments: call.Function.Arguments}}); err != nil {
					return err
				}
			}
		}
		return nil
	})
	if err != nil && !errors.Is(err, errLLMStreamDone) {
		return err
	}
	if !done {
		return errors.New("llm stream ended before [DONE]")
	}
	return nil
}

// readSSEData parses SSE records across arbitrary transport chunk boundaries and
// supports CRLF and multi-line data fields.
func readSSEData(ctx context.Context, input io.Reader, consume func([]byte) error) error {
	reader := bufio.NewReader(input)
	var dataLines [][]byte
	dispatch := func() error {
		if len(dataLines) == 0 {
			return nil
		}
		data := bytes.Join(dataLines, []byte("\n"))
		dataLines = dataLines[:0]
		return consume(data)
	}
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		line, err := reader.ReadString('\n')
		if err != nil && !errors.Is(err, io.EOF) {
			return fmt.Errorf("read llm stream: %w", err)
		}
		line = strings.TrimSuffix(line, "\n")
		line = strings.TrimSuffix(line, "\r")
		if line == "" {
			if dispatchErr := dispatch(); dispatchErr != nil {
				return dispatchErr
			}
		} else if strings.HasPrefix(line, "data:") {
			value := strings.TrimPrefix(line, "data:")
			value = strings.TrimPrefix(value, " ")
			dataLines = append(dataLines, []byte(value))
		}
		if errors.Is(err, io.EOF) {
			if line != "" {
				return dispatch()
			}
			return nil
		}
	}
}
