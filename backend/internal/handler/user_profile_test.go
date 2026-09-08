package handler

import (
	"testing"

	"medicalagent/internal/model"
)

func TestValidateRequiredUserProfile(t *testing.T) {
	tests := []struct {
		name        string
		affiliation string
		title       string
		wantMessage string
	}{
		{name: "valid", affiliation: " 北京中医药大学 ", title: " 研究员 ", wantMessage: ""},
		{name: "missing affiliation", title: "研究员", wantMessage: "单位不能为空"},
		{name: "missing title", affiliation: "北京中医药大学", wantMessage: "职称不能为空"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			user := &model.User{Affiliation: tt.affiliation, ProfessionalTitle: tt.title}
			if got := validateRequiredUserProfile(user); got != tt.wantMessage {
				t.Fatalf("validateRequiredUserProfile() = %q, want %q", got, tt.wantMessage)
			}
			if tt.wantMessage == "" && (user.Affiliation != "北京中医药大学" || user.ProfessionalTitle != "研究员") {
				t.Fatalf("profile values were not trimmed: %#v", user)
			}
		})
	}
}
