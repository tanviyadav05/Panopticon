package main

import (
	"fmt"
	"log"
	"net/http"
	"runtime/debug"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func withLogging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		log.Printf("%s %s %d %s", r.Method, r.URL.Path, rec.status, time.Since(start))
	})
}

// ---------------------------------------------------------------------------
// Panic recovery — an ordinary safety net, deliberately present so that a
// crash in a handler degrades to a 500 instead of taking the whole process
// (and Observer's view of "is the app alive") down with it.
// ---------------------------------------------------------------------------

func withRecover(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if err := recover(); err != nil {
				log.Printf("panic recovered: %v\n%s", err, debug.Stack())
				writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "internal_error"})
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// ---------------------------------------------------------------------------
// Request metrics — a minimal, dependency-free counter set exposed at
// /metrics in a Prometheus-ish text format. Real deployments would swap this
// for client_golang; this keeps the demo dependency-light while still giving
// Observer/monitoring something real to scrape.
// ---------------------------------------------------------------------------

type metricsCounter struct {
	totalRequests int64
	totalErrors   int64
	byPath        sync.Map // path -> *int64
}

var requestMetrics = &metricsCounter{}
var labWorkloads = &labWorkloadController{}

func withRequestMetrics(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)

		atomic.AddInt64(&requestMetrics.totalRequests, 1)
		if rec.status >= 500 {
			atomic.AddInt64(&requestMetrics.totalErrors, 1)
		}
		key := normalizePath(r.URL.Path)
		counterAny, _ := requestMetrics.byPath.LoadOrStore(key, new(int64))
		atomic.AddInt64(counterAny.(*int64), 1)
	})
}

// normalizePath collapses path-like params so /api/users and /api/users?x=1
// land in the same bucket, and so a flood of distinct query strings can't
// blow up the metrics map's cardinality — itself a small, real defense.
func normalizePath(p string) string {
	if i := strings.IndexByte(p, '?'); i >= 0 {
		p = p[:i]
	}
	return p
}

type metricsSnapshot struct {
	totalRequests int64
	totalErrors   int64
	byPath        map[string]int64
}

func (m *metricsCounter) snapshot() metricsSnapshot {
	snap := metricsSnapshot{
		totalRequests: atomic.LoadInt64(&m.totalRequests),
		totalErrors:   atomic.LoadInt64(&m.totalErrors),
		byPath:        map[string]int64{},
	}
	m.byPath.Range(func(k, v any) bool {
		snap.byPath[k.(string)] = atomic.LoadInt64(v.(*int64))
		return true
	})
	return snap
}

func (s metricsSnapshot) prometheusFormat() string {
	var b strings.Builder
	fmt.Fprintf(&b, "# HELP target_app_requests_total Total HTTP requests received\n")
	fmt.Fprintf(&b, "# TYPE target_app_requests_total counter\n")
	fmt.Fprintf(&b, "target_app_requests_total %d\n", s.totalRequests)
	fmt.Fprintf(&b, "# HELP target_app_errors_total Total HTTP 5xx responses\n")
	fmt.Fprintf(&b, "# TYPE target_app_errors_total counter\n")
	fmt.Fprintf(&b, "target_app_errors_total %d\n", s.totalErrors)
	fmt.Fprintf(&b, "# HELP target_app_requests_by_path_total Requests per route\n")
	fmt.Fprintf(&b, "# TYPE target_app_requests_by_path_total counter\n")
	for path, count := range s.byPath {
		fmt.Fprintf(&b, "target_app_requests_by_path_total{path=%q} %d\n", path, count)
	}
	b.WriteString(labWorkloads.prometheusFormat())
	return b.String()
}

func itoa(value int) string     { return fmt.Sprintf("%d", value) }
func uitoa(value uint64) string { return fmt.Sprintf("%d", value) }
