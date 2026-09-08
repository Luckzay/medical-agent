package repository

import "testing"

func TestImportedContentPrimaryKeysMatchSchema(t *testing.T) {
	if got := publicTableKeys["cases"]; got != "case_id" {
		t.Fatalf("cases primary key = %q, want case_id", got)
	}
	if got := publicTableKeys["clauses"]; got != "clause_id" {
		t.Fatalf("clauses primary key = %q, want clause_id", got)
	}
}

func TestIsWithinGuestRecords(t *testing.T) {
	firstTwenty := []int64{2, 4, 7, 11, 15, 20, 21, 30, 31, 40, 42, 50, 60, 70, 80, 90, 100, 110, 120, 130}
	if !IsWithinGuestRecords(firstTwenty, int64(130)) {
		t.Fatal("the twentieth record should be accessible")
	}
	if IsWithinGuestRecords(firstTwenty, int64(131)) {
		t.Fatal("a record outside the first twenty should not be accessible")
	}
	if IsWithinGuestRecords(firstTwenty, int64(1)) {
		t.Fatal("ID magnitude must not be used instead of ordered membership")
	}
}
