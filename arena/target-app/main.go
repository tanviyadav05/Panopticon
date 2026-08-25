// Command target-app is the deliberately-vulnerable service that lives at the
// center of the Arena. It is intentionally a very ordinary-looking Go HTTP
// service — the point is that the weak points are concentrated in
// vulnerabilities.go, not scattered through "clever" code, so they're easy
// to reason about and easy for Blue/Observer to learn against.
package main

import (
	"context"
	"database/sql"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/lib/pq"
)

func main() {
	port := getenv("PORT", "8080")
	dbURL := os.Getenv("DATABASE_URL")
	debug := os.Getenv("PANOPTICON_DEBUG") == "1"

	store, closeStore := mustBuildStore(dbURL)
	defer closeStore()

	srv := &server{store: store, debug: debug, startedAt: time.Now()}

	mux := http.NewServeMux()
	srv.routes(mux)

	handler := withRecover(withRequestMetrics(withLogging(mux)))

	httpServer := &http.Server{
		Addr:         ":" + port,
		Handler:      handler,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("target-app: listening on :%s (debug=%v, db=%v)", port, debug, dbURL != "")
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("target-app: server error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	log.Println("target-app: shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(ctx); err != nil {
		log.Printf("target-app: graceful shutdown failed: %v", err)
	}
}

func mustBuildStore(dbURL string) (Store, func()) {
	if dbURL == "" {
		log.Println("target-app: DATABASE_URL not set, using in-memory store (dev/test mode)")
		return newMemoryStore(), func() {}
	}

	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		log.Fatalf("target-app: failed to open database: %v", err)
	}
	db.SetMaxOpenConns(20)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	if err := db.Ping(); err != nil {
		// Don't crash the process on a slow/late-starting Postgres pod —
		// log and keep retrying on each request instead.
		log.Printf("target-app: database unreachable at startup (%v); will retry on demand", err)
	} else {
		if err := ensureSchema(db); err != nil {
			log.Fatalf("target-app: failed to ensure schema: %v", err)
		}
		log.Println("target-app: using Postgres store")
	}

	return &postgresStore{db: db}, func() { _ = db.Close() }
}

func ensureSchema(db *sql.DB) error {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS users (
			id SERIAL PRIMARY KEY,
			name TEXT NOT NULL,
			email TEXT NOT NULL
		);
		CREATE TABLE IF NOT EXISTS orders (
			id SERIAL PRIMARY KEY,
			user_id INTEGER REFERENCES users(id),
			item TEXT NOT NULL,
			created_at TIMESTAMPTZ NOT NULL DEFAULT now()
		);
	`)
	return err
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
