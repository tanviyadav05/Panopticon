package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMemoryStoreListAndCreateUser(t *testing.T) {
	store := newMemoryStore()
	ctx := context.Background()

	users, err := store.ListUsers(ctx)
	if err != nil {
		t.Fatalf("ListUsers: %v", err)
	}
	if len(users) != 3 {
		t.Fatalf("expected 3 seeded users, got %d", len(users))
	}

	created, err := store.CreateUser(ctx, User{Name: "Margaret Hamilton", Email: "margaret@example.com"})
	if err != nil {
		t.Fatalf("CreateUser: %v", err)
	}
	if created.ID != 4 {
		t.Fatalf("expected new user id 4, got %d", created.ID)
	}

	users, _ = store.ListUsers(ctx)
	if len(users) != 4 {
		t.Fatalf("expected 4 users after create, got %d", len(users))
	}
}

func TestMemoryStoreSearch(t *testing.T) {
	store := newMemoryStore()
	ctx := context.Background()

	results, err := store.SearchUsers(ctx, "grace")
	if err != nil {
		t.Fatalf("SearchUsers: %v", err)
	}
	if len(results) != 1 || results[0].Name != "Grace Hopper" {
		t.Fatalf("expected to find Grace Hopper, got %+v", results)
	}

	results, _ = store.SearchUsers(ctx, "")
	if len(results) != 3 {
		t.Fatalf("expected empty query to match everyone, got %d", len(results))
	}
}

func TestHandleHealth(t *testing.T) {
	srv := &server{store: newMemoryStore()}
	mux := http.NewServeMux()
	srv.routes(mux)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var body map[string]string
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body["status"] != "ok" {
		t.Fatalf("expected status ok, got %v", body)
	}
}

func TestHandleCreateAndListUsers(t *testing.T) {
	srv := &server{store: newMemoryStore()}
	mux := http.NewServeMux()
	srv.routes(mux)

	payload, _ := json.Marshal(User{Name: "Hedy Lamarr", Email: "hedy@example.com"})
	req := httptest.NewRequest(http.MethodPost, "/api/users", bytes.NewReader(payload))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodGet, "/api/users", nil)
	rec = httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	var users []User
	if err := json.NewDecoder(rec.Body).Decode(&users); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(users) != 4 {
		t.Fatalf("expected 4 users, got %d", len(users))
	}
}

func TestHandleEchoRespectsBodyCap(t *testing.T) {
	srv := &server{store: newMemoryStore()}
	mux := http.NewServeMux()
	srv.routes(mux)

	body := strings.NewReader("hello observer")
	req := httptest.NewRequest(http.MethodPost, "/api/echo", body)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var resp map[string]int64
	json.NewDecoder(rec.Body).Decode(&resp)
	if resp["received_bytes"] != int64(len("hello observer")) {
		t.Fatalf("unexpected byte count: %+v", resp)
	}
}

// --- vulnerability surface tests -------------------------------------------
// These tests document the shape of the two intentional flaws — they prove
// the flaw exists in the query/path construction, not how to exploit either
// one against a live target.

func TestBuildSearchQueryIsUnparameterized(t *testing.T) {
	q := BuildSearchQuery("o'reilly")
	if !strings.Contains(q, "o'reilly") {
		t.Fatalf("expected raw input to appear verbatim in the query string, got: %s", q)
	}
	if strings.Contains(q, "$1") {
		t.Fatalf("query unexpectedly looks parameterized: %s", q)
	}
}

func TestResolveFilePathDoesNotContainTraversal(t *testing.T) {
	p := ResolveFilePath("../../../etc/hostname")
	if !looksLikeTraversal("../../../etc/hostname") {
		t.Fatalf("traversal detector helper itself is broken")
	}
	if !strings.Contains(p, "..") {
		t.Fatalf("expected the unsanitized path to retain '..', got: %s", p)
	}
}

func TestResolveFilePathDefaultsWhenEmpty(t *testing.T) {
	p := ResolveFilePath("")
	if !strings.HasSuffix(p, "welcome.txt") {
		t.Fatalf("expected default welcome.txt, got: %s", p)
	}
}
