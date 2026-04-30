# GPU Crash Test — HyperPod Resiliency Testing
#
# Usage:
#   make crash          # Python version, crash GPU 0 (infinite loop)
#   make crash GPU=1    # Python version, crash GPU 1
#   make crash-all      # Python version, crash ALL GPUs
#   make crash-memfault # Python version, illegal memory access
#   make build          # Build C/CUDA version
#   make crash-c        # C version, crash GPU 0
#   make check          # Verify GPU health before/after test

GPU ?= 0
METHOD ?= hang
NVCC ?= nvcc
NVCC_FLAGS ?= -O2
PYTHON ?= .venv/bin/python

.PHONY: help crash crash-all crash-memfault crash-c build clean check check-dmesg

help:
	@echo "GPU Crash Test — HyperPod Resiliency Testing"
	@echo ""
	@echo "Python version (recommended — no build step):"
	@echo "  make crash              Crash GPU 0 with infinite loop"
	@echo "  make crash GPU=1        Crash GPU 1"
	@echo "  make crash-all          Crash ALL GPUs (nuclear option)"
	@echo "  make crash-memfault     Crash GPU 0 with illegal memory access"
	@echo ""
	@echo "C/CUDA version (if no Python CUDA library available):"
	@echo "  make build              Build the C/CUDA binary"
	@echo "  make crash-c            Crash GPU 0 with C version"
	@echo "  make crash-c GPU=1      Crash GPU 1 with C version"
	@echo ""
	@echo "Diagnostics:"
	@echo "  make check              Show GPU health status"
	@echo "  make check-dmesg        Show recent Xid errors from dmesg"
	@echo "  make clean              Remove build artifacts"

# --- Python version ---

crash: .venv/.installed
	$(PYTHON) crash_gpu.py --gpu $(GPU) --method $(METHOD)

crash-all: .venv/.installed
	$(PYTHON) crash_gpu.py --gpu all --method $(METHOD)

crash-memfault: .venv/.installed
	$(PYTHON) crash_gpu.py --gpu $(GPU) --method memfault

# --- C/CUDA version ---

build: crash_gpu_c

crash_gpu_c: crash_gpu.cu
	$(NVCC) $(NVCC_FLAGS) -o $@ $<

crash-c: crash_gpu_c
	./crash_gpu_c $(GPU) $(METHOD)

# --- Diagnostics ---

check:
	@echo "=== GPU Health Check ==="
	@nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,ecc.errors.uncorrected.volatile.total --format=csv 2>/dev/null || echo "nvidia-smi failed — GPU may be in a bad state"
	@echo ""
	@echo "=== Recent Xid Errors ==="
	@dmesg 2>/dev/null | grep -i "xid" | tail -20 || echo "(no Xid errors found or dmesg not accessible)"

check-dmesg:
	@echo "=== Recent GPU/NVIDIA kernel messages ==="
	@dmesg 2>/dev/null | grep -iE "(nvidia|xid|nvrm|gpu|pci.*10de)" | tail -40 || echo "(no relevant messages or dmesg not accessible)"

# --- Setup ---

venv: .venv/.done
.venv/.done:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	@touch $@

install: .venv/.installed
.venv/.installed: .venv/.done
	.venv/bin/pip install numpy pycuda
	@touch $@

# --- Cleanup ---

clean:
	rm -f crash_gpu_c
	rm -rf .venv
