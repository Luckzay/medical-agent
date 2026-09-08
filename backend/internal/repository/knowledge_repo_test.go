package repository

import "testing"

func TestEscapeLikeEscapesWildcards(t *testing.T) {
	if got, want := escapeLike(`a%b_c\d`), `a\%b\_c\\d`; got != want {
		t.Fatalf("escapeLike() = %q, want %q", got, want)
	}
}
