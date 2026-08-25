package main

import (
	"context"
	"crypto/subtle"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

type User struct {
	ID    int    `json:"id"`
	Name  string `json:"name"`
	Email string `json:"email"`
}

type Order struct {
	ID        int       `json:"id"`
	UserID    int       `json:"user_id"`
	Item      string    `json:"item"`
	CreatedAt time.Time `json:"created_at"`
}

// Store abstracts persistence so the service can run standalone (in-memory,
// for local dev and the tests in main_test.go) or against the real Postgres
// instance defined in arena/k8s/01-postgres.yaml.
type Store interface {
	ListUsers(ctx context.Context) ([]User, error)
	CreateUser(ctx context.Context, u User) (User, error)
	SearchUsers(ctx context.Context, rawQuery string) ([]User, error)
	CreateOrder(ctx context.Context, o Order) (Order, error)
	Ping(ctx context.Context) error
}

// ---------------------------------------------------------------------------
// In-memory store — used when DATABASE_URL is unset
// ---------------------------------------------------------------------------

type memoryStore struct {
	mu      sync.Mutex
	users   []User
	orders  []Order
	nextUID int
	nextOID int
}

func newMemoryStore() *memoryStore {
	return &memoryStore{
		users: []User{
			{ID: 1, Name: "Ada Lovelace", Email: "ada@example.com"},
			{ID: 2, Name: "Grace Hopper", Email: "grace@example.com"},
			{ID: 3, Name: "Katherine Johnson", Email: "katherine@example.com"},
		},
		nextUID: 4,
		nextOID: 1,
	}
}

func (m *memoryStore) ListUsers(ctx context.Context) ([]User, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]User, len(m.users))
	copy(out, m.users)
	return out, nil
}

func (m *memoryStore) CreateUser(ctx context.Context, u User) (User, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	u.ID = m.nextUID
	m.nextUID++
	m.users = append(m.users, u)
	return u, nil
}

// SearchUsers in memory mode does NOT execute SQL (there's no database to
// inject into), but it deliberately runs the *same* vulnerable query-builder
// from vulnerabilities.go so the resulting query string is identical to what
// would be sent to Postgres in production mode. That string is only ever
// surfaced back to the caller when PANOPTICON_DEBUG=1, purely so a learner
// can see the shape of the injection surface without anything actually being
// exploitable in this mode.
func (m *memoryStore) SearchUsers(ctx context.Context, rawQuery string) ([]User, error) {
	_ = BuildSearchQuery(rawQuery) // constructed for parity with prod mode; not executed here
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []User
	needle := rawQuery
	for _, u := range m.users {
		if containsFold(u.Name, needle) || containsFold(u.Email, needle) {
			out = append(out, u)
		}
	}
	return out, nil
}

func (m *memoryStore) CreateOrder(ctx context.Context, o Order) (Order, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	o.ID = m.nextOID
	m.nextOID++
	o.CreatedAt = time.Now().UTC()
	m.orders = append(m.orders, o)
	return o, nil
}

func (m *memoryStore) Ping(ctx context.Context) error { return nil }

func containsFold(haystack, needle string) bool {
	if needle == "" {
		return true
	}
	toLower := func(s string) string {
		b := []byte(s)
		for i, c := range b {
			if c >= 'A' && c <= 'Z' {
				b[i] = c + 'a' - 'A'
			}
		}
		return string(b)
	}
	hl, nl := toLower(haystack), toLower(needle)
	for i := 0; i+len(nl) <= len(hl); i++ {
		if hl[i:i+len(nl)] == nl {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// Postgres store — used when DATABASE_URL is set (the real Arena deployment)
// ---------------------------------------------------------------------------

type postgresStore struct {
	db *sql.DB
}

func (p *postgresStore) ListUsers(ctx context.Context) ([]User, error) {
	rows, err := p.db.QueryContext(ctx, `SELECT id, name, email FROM users ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []User
	for rows.Next() {
		var u User
		if err := rows.Scan(&u.ID, &u.Name, &u.Email); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func (p *postgresStore) CreateUser(ctx context.Context, u User) (User, error) {
	row := p.db.QueryRowContext(ctx,
		`INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id`, u.Name, u.Email)
	if err := row.Scan(&u.ID); err != nil {
		return User{}, err
	}
	return u, nil
}

// SearchUsers is the real, live version of the intentionally-vulnerable
// search path: it executes whatever string vulnerabilities.go hands back,
// unparameterized, exactly as a careless implementation would in the real
// world. This is the training signal Blue's anomaly_detector.py and Red's
// telemetry-side reward are meant to key off of — see docs/threat_model.md.
func (p *postgresStore) SearchUsers(ctx context.Context, rawQuery string) ([]User, error) {
	query := BuildSearchQuery(rawQuery)
	rows, err := p.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []User
	for rows.Next() {
		var u User
		if err := rows.Scan(&u.ID, &u.Name, &u.Email); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func (p *postgresStore) CreateOrder(ctx context.Context, o Order) (Order, error) {
	row := p.db.QueryRowContext(ctx,
		`INSERT INTO orders (user_id, item) VALUES ($1, $2) RETURNING id, created_at`, o.UserID, o.Item)
	if err := row.Scan(&o.ID, &o.CreatedAt); err != nil {
		return Order{}, err
	}
	return o, nil
}

func (p *postgresStore) Ping(ctx context.Context) error { return p.db.PingContext(ctx) }

// ---------------------------------------------------------------------------
// HTTP layer
// ---------------------------------------------------------------------------

type server struct {
	store     Store
	debug     bool
	startedAt time.Time
}

func (s *server) routes(mux *http.ServeMux) {
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /metrics", s.handleMetrics)
	mux.HandleFunc("GET /api/users", s.handleListUsers)
	mux.HandleFunc("POST /api/users", s.handleCreateUser)
	mux.HandleFunc("GET /api/search", s.handleSearch)
	mux.HandleFunc("GET /api/files", s.handleFiles)
	mux.HandleFunc("POST /api/orders", s.handleCreateOrder)
	mux.HandleFunc("POST /api/echo", s.handleEcho)
	mux.HandleFunc("GET /api/lab/workload/status", s.handleLabWorkloadStatus)
	mux.HandleFunc("POST /api/lab/workload/cpu", s.handleLabCPUWorkload)
	mux.HandleFunc("POST /api/lab/workload/memory", s.handleLabMemoryWorkload)
	mux.HandleFunc("POST /api/lab/workload/stop", s.handleLabWorkloadStop)
}

func (s *server) requireLabControl(w http.ResponseWriter, r *http.Request) bool {
	if os.Getenv("PANOPTICON_LAB_WORKLOADS_ARMED") != "1" {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "lab_workloads_disarmed"})
		return false
	}
	want := os.Getenv("PANOPTICON_LAB_CONTROL_TOKEN")
	got := r.Header.Get("X-Panopticon-Lab-Token")
	if want == "" {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "lab_control_token_not_configured"})
		return false
	}
	if subtle.ConstantTimeCompare([]byte(want), []byte(got)) != 1 {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid_lab_control_token"})
		return false
	}
	return true
}

func (s *server) handleLabWorkloadStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, labWorkloads.Status())
}

func (s *server) handleLabCPUWorkload(w http.ResponseWriter, r *http.Request) {
	if !s.requireLabControl(w, r) {
		return
	}
	writeJSON(w, http.StatusAccepted, labWorkloads.StartCPU())
}

func (s *server) handleLabMemoryWorkload(w http.ResponseWriter, r *http.Request) {
	if !s.requireLabControl(w, r) {
		return
	}
	writeJSON(w, http.StatusAccepted, labWorkloads.StartMemory())
}

func (s *server) handleLabWorkloadStop(w http.ResponseWriter, r *http.Request) {
	if !s.requireLabControl(w, r) {
		return
	}
	writeJSON(w, http.StatusOK, labWorkloads.Stop())
}

func (s *server) handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	status := "ok"
	if err := s.store.Ping(ctx); err != nil {
		status = "degraded"
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"status": status,
		"uptime": time.Since(s.startedAt).String(),
	})
}

func (s *server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	snap := requestMetrics.snapshot()
	w.Write([]byte(snap.prometheusFormat()))
}

func (s *server) handleListUsers(w http.ResponseWriter, r *http.Request) {
	users, err := s.store.ListUsers(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "list_users_failed"})
		return
	}
	writeJSON(w, http.StatusOK, users)
}

func (s *server) handleCreateUser(w http.ResponseWriter, r *http.Request) {
	var u User
	if err := json.NewDecoder(r.Body).Decode(&u); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}
	if u.Name == "" || u.Email == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "name_and_email_required"})
		return
	}
	created, err := s.store.CreateUser(r.Context(), u)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "create_user_failed"})
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

// handleSearch is the deliberately-vulnerable endpoint: ?q= is forwarded,
// unsanitized, into a SQL query when running against Postgres. See
// vulnerabilities.go for the actual flaw and docs/threat_model.md for the
// containment assumptions this depends on.
func (s *server) handleSearch(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	results, err := s.store.SearchUsers(r.Context(), q)
	if err != nil {
		resp := map[string]string{"error": "search_failed"}
		if s.debug {
			resp["detail"] = err.Error()
		}
		writeJSON(w, http.StatusInternalServerError, resp)
		return
	}
	body := map[string]any{"results": results}
	if s.debug {
		body["_debug_query"] = BuildSearchQuery(q)
	}
	writeJSON(w, http.StatusOK, body)
}

// handleFiles is the deliberately-vulnerable file endpoint: ?name= is
// resolved against a base directory without stripping ".." segments. See
// vulnerabilities.go.
func (s *server) handleFiles(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("name")
	path := ResolveFilePath(name)

	data, err := os.ReadFile(path)
	if err != nil {
		resp := map[string]string{"error": "not_found"}
		if s.debug {
			resp["_debug_path"] = path
		}
		writeJSON(w, http.StatusNotFound, resp)
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Write(data)
}

func (s *server) handleCreateOrder(w http.ResponseWriter, r *http.Request) {
	var o Order
	if err := json.NewDecoder(r.Body).Decode(&o); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_json"})
		return
	}
	if o.UserID == 0 || o.Item == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "user_id_and_item_required"})
		return
	}
	created, err := s.store.CreateOrder(r.Context(), o)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "create_order_failed"})
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

// handleEcho is intentionally boring: it just reflects how many bytes it
// received. It exists as a harmless, stable endpoint for Observer's network
// probe and any connection-handling tests to point at without touching the
// database. The MaxBytesReader cap is the kind of defensive basic that
// vulnerabilities.go's targets deliberately skip.
func (s *server) handleEcho(w http.ResponseWriter, r *http.Request) {
	const maxBody = 1 << 20 // 1 MiB
	r.Body = http.MaxBytesReader(w, r.Body, maxBody)
	n, err := io.Copy(io.Discard, r.Body)
	if err != nil {
		writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "body_too_large"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]int64{"received_bytes": n})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

var (
	_ = strconv.Itoa
	_ = filepath.Clean
)
