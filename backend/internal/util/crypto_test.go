package util

import (
	"testing"
)

func TestCrypto(t *testing.T) {
	key := []byte("12345678901234567890123456789012") // 32 bytes
	plaintext := "hello world"

	encrypted, err := Encrypt(plaintext, key)
	if err != nil {
		t.Fatalf("Encrypt failed: %v", err)
	}

	decrypted, err := Decrypt(encrypted, key)
	if err != nil {
		t.Fatalf("Decrypt failed: %v", err)
	}

	if decrypted != plaintext {
		t.Errorf("Expected %s, got %s", plaintext, decrypted)
	}
}

func TestParseMasterKey(t *testing.T) {
	rawKey := "12345678901234567890123456789012"
	parsed, err := ParseMasterKey(rawKey)
	if err != nil || len(parsed) != 32 {
		t.Errorf("Failed to parse raw key: %v", err)
	}

	b64Key := "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI="
	parsed, err = ParseMasterKey(b64Key)
	if err != nil || len(parsed) != 32 {
		t.Errorf("Failed to parse b64 key: %v", err)
	}
}
