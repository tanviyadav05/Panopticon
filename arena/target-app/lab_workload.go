package main

// This file implements the intentionally small, bounded workload used by the
// Panopticon lab demo. It is not a general stress API: callers cannot choose
// a host, duration, worker count, or allocation size. The constants below,
// together with the Pod resource limits, are the safety boundary.

import (
	"context"
	"crypto/sha256"
	"runtime"
	"sync"
	"time"
)

const (
	labCPUWorkers       = 1
	labMemoryBytes      = 48 * 1024 * 1024
	labWorkloadDuration = 15 * time.Second
)

type labWorkloadStatus struct {
	CPUActive       bool   `json:"cpu_active"`
	MemoryActive    bool   `json:"memory_active"`
	MemoryBytes     int    `json:"memory_bytes"`
	CPUWorkers      int    `json:"cpu_workers"`
	DurationSeconds int    `json:"duration_seconds"`
	CPUSessions     uint64 `json:"cpu_sessions"`
	MemorySessions  uint64 `json:"memory_sessions"`
}

type labWorkloadController struct {
	mu               sync.Mutex
	cpuCancel        context.CancelFunc
	cpuActive        bool
	cpuGeneration    uint64
	memory           []byte
	memoryGeneration uint64
	cpuSessions      uint64
	memorySessions   uint64
}

func (c *labWorkloadController) statusLocked() labWorkloadStatus {
	return labWorkloadStatus{
		CPUActive:       c.cpuActive,
		MemoryActive:    len(c.memory) > 0,
		MemoryBytes:     len(c.memory),
		CPUWorkers:      labCPUWorkers,
		DurationSeconds: int(labWorkloadDuration.Seconds()),
		CPUSessions:     c.cpuSessions,
		MemorySessions:  c.memorySessions,
	}
}

func (c *labWorkloadController) Status() labWorkloadStatus {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.statusLocked()
}

func (c *labWorkloadController) stopCPULocked() {
	c.cpuGeneration++
	if c.cpuCancel != nil {
		c.cpuCancel()
		c.cpuCancel = nil
	}
	c.cpuActive = false
}

func (c *labWorkloadController) StartCPU() labWorkloadStatus {
	c.mu.Lock()
	c.stopCPULocked()
	ctx, cancel := context.WithCancel(context.Background())
	c.cpuCancel = cancel
	c.cpuActive = true
	c.cpuSessions++
	generation := c.cpuGeneration
	c.mu.Unlock()

	for worker := 0; worker < labCPUWorkers; worker++ {
		go func(seed byte) {
			block := [32]byte{seed}
			for {
				select {
				case <-ctx.Done():
					return
				default:
					block = sha256.Sum256(block[:])
				}
			}
		}(byte(worker + 1))
	}

	go func() {
		time.Sleep(labWorkloadDuration)
		c.mu.Lock()
		defer c.mu.Unlock()
		if c.cpuGeneration == generation {
			c.stopCPULocked()
		}
	}()

	return c.Status()
}

func (c *labWorkloadController) StartMemory() labWorkloadStatus {
	// Touch each page so RSS reflects the bounded allocation in the Observer.
	allocation := make([]byte, labMemoryBytes)
	for i := 0; i < len(allocation); i += 4096 {
		allocation[i] = byte(i)
	}

	c.mu.Lock()
	c.memoryGeneration++
	generation := c.memoryGeneration
	c.memory = allocation
	c.memorySessions++
	c.mu.Unlock()

	go func() {
		time.Sleep(labWorkloadDuration)
		c.mu.Lock()
		if c.memoryGeneration == generation {
			c.memory = nil
		}
		c.mu.Unlock()
		runtime.GC()
	}()

	return c.Status()
}

func (c *labWorkloadController) Stop() labWorkloadStatus {
	c.mu.Lock()
	c.stopCPULocked()
	c.memoryGeneration++
	c.memory = nil
	c.mu.Unlock()
	runtime.GC()
	return c.Status()
}

func (c *labWorkloadController) prometheusFormat() string {
	status := c.Status()
	cpuActive, memoryActive := 0, 0
	if status.CPUActive {
		cpuActive = 1
	}
	if status.MemoryActive {
		memoryActive = 1
	}
	return "# HELP target_app_lab_workload_cpu_active Whether the bounded CPU lab workload is active\n" +
		"# TYPE target_app_lab_workload_cpu_active gauge\n" +
		"target_app_lab_workload_cpu_active " + itoa(cpuActive) + "\n" +
		"# HELP target_app_lab_workload_memory_bytes Bytes held by the bounded memory lab workload\n" +
		"# TYPE target_app_lab_workload_memory_bytes gauge\n" +
		"target_app_lab_workload_memory_bytes " + itoa(status.MemoryBytes) + "\n" +
		"# HELP target_app_lab_workload_memory_active Whether the bounded memory lab workload is active\n" +
		"# TYPE target_app_lab_workload_memory_active gauge\n" +
		"target_app_lab_workload_memory_active " + itoa(memoryActive) + "\n" +
		"# HELP target_app_lab_workload_sessions_total Bounded lab workload sessions\n" +
		"# TYPE target_app_lab_workload_sessions_total counter\n" +
		"target_app_lab_workload_sessions_total{kind=\"cpu\"} " + uitoa(status.CPUSessions) + "\n" +
		"target_app_lab_workload_sessions_total{kind=\"memory\"} " + uitoa(status.MemorySessions) + "\n"
}
