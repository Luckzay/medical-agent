package handler

import (
	"net/http/httptest"
	"testing"

	"medicalagent/internal/model"

	"github.com/gin-gonic/gin"
)

func TestPublicPaginationGuestIsClamped(t *testing.T) {
	gin.SetMode(gin.TestMode)
	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	c.Request = httptest.NewRequest("GET", "/api/herbs?page=9&page_size=200", nil)

	page, pageSize, guest := publicPagination(c)
	if page != 1 || pageSize != 20 || !guest {
		t.Fatalf("publicPagination() = (%d, %d, %v), want (1, 20, true)", page, pageSize, guest)
	}
	if total := publicTotal(99, guest); total != 20 {
		t.Fatalf("publicTotal() = %d, want 20", total)
	}
}

func TestPublicPaginationAuthenticatedIsUnrestricted(t *testing.T) {
	gin.SetMode(gin.TestMode)
	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	c.Request = httptest.NewRequest("GET", "/api/herbs?page=3&page_size=100", nil)
	c.Set("authenticated", true)

	page, pageSize, guest := publicPagination(c)
	if page != 3 || pageSize != 100 || guest {
		t.Fatalf("publicPagination() = (%d, %d, %v), want (3, 100, false)", page, pageSize, guest)
	}
}

func TestPrepareRegistrationForcesPendingUser(t *testing.T) {
	user := &model.User{Role: "admin", Status: model.UserStatusActive}
	prepareRegistration(user)
	if user.Role != "user" || user.Status != model.UserStatusPending {
		t.Fatalf("registration defaults = role %q status %q", user.Role, user.Status)
	}
}

func TestPrepareAdminCreatedUserDefaultsActive(t *testing.T) {
	user := &model.User{}
	prepareAdminCreatedUser(user)
	if user.Role != "user" || user.Status != model.UserStatusActive {
		t.Fatalf("admin create defaults = role %q status %q", user.Role, user.Status)
	}
}
