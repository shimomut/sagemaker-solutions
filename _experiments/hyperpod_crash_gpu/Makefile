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

# Resolve GPU index to PCI bus ID in short form for nvidia-smi drain (e.g. 0000:00:1E.0)
PCI_BUS_ID = $(shell nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader -i $(GPU) 2>/dev/null | sed 's/^0000//')
# Lowercase version for sysfs paths (e.g. 0000:00:1e.0)
PCI_SYSFS_ID = $(shell echo $(PCI_BUS_ID) | tr 'A-Z' 'a-z')

.PHONY: help crash crash-all crash-memfault crash-c build clean check check-dmesg \
        drain undrain pci-remove pci-rescan recover watch-dmesg

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
	@echo "Hardware-level (requires sudo, simulates real GPU failure):"
	@echo "  make drain              Drain GPU 0 via nvidia-smi (marks unusable)"
	@echo "  make undrain            Undo drain on GPU 0"
	@echo "  make pci-remove         Remove GPU 0 from PCIe bus (simulates HW failure)"
	@echo "  make pci-rescan         Rescan PCIe bus to rediscover removed GPU"
	@echo "  make recover            Full recovery: undrain + PCIe rescan"
	@echo ""
	@echo "Diagnostics:"
	@echo "  make check              Show GPU health status"
	@echo "  make check-dmesg        Show recent Xid errors from dmesg"
	@echo "  make watch-dmesg        Follow dmesg for GPU messages (live)"
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

# --- Hardware-level methods (require sudo) ---

drain:
	@echo "=== Draining GPU $(GPU) [$(PCI_BUS_ID)] ==="
	sudo nvidia-smi -pm 0 -i $(GPU)
	sudo nvidia-smi drain -p $(PCI_BUS_ID) -m 1
	@echo "GPU $(GPU) is now draining. nvidia-smi will show it as unusable."

undrain:
	@echo "=== Undraining GPU $(GPU) [$(PCI_BUS_ID)] ==="
	sudo nvidia-smi drain -p $(PCI_BUS_ID) -m 0
	sudo nvidia-smi -pm 1 -i $(GPU)
	@echo "GPU $(GPU) drain cleared."

pci-remove:
	@echo "=== Removing GPU $(GPU) [$(PCI_BUS_ID)] from PCIe bus ==="
	@echo "⚠️  This simulates a hardware failure. The GPU will disappear from the system."
	@echo "    Recovery: make pci-rescan"
	sudo bash -c 'echo 1 > /sys/bus/pci/devices/$(PCI_SYSFS_ID)/remove'
	@echo "GPU $(GPU) removed from PCIe bus."

pci-rescan:
	@echo "=== Rescanning PCIe bus to rediscover GPUs ==="
	sudo bash -c 'echo 1 > /sys/bus/pci/rescan'
	@sleep 2
	@echo "PCIe rescan complete. Current GPUs:"
	@nvidia-smi --query-gpu=index,name,pci.bus_id --format=csv 2>/dev/null || echo "nvidia-smi failed — driver may need reload"

recover:
	@echo "=== Full GPU recovery ==="
	-sudo nvidia-smi drain -p $(PCI_BUS_ID) -m 0 2>/dev/null
	sudo bash -c 'echo 1 > /sys/bus/pci/rescan'
	@sleep 2
	-sudo nvidia-smi -pm 1 -i $(GPU) 2>/dev/null
	@echo "Recovery complete. Current GPUs:"
	@nvidia-smi --query-gpu=index,name,pci.bus_id --format=csv 2>/dev/null || echo "nvidia-smi failed — driver may need reload"

# --- Diagnostics ---

check:
	@echo "=== GPU Health Check ==="
	@nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,ecc.errors.uncorrected.volatile.total --format=csv 2>/dev/null || echo "nvidia-smi failed — GPU may be in a bad state"
	@echo ""
	@echo "=== Recent Xid Errors ==="
	@sudo dmesg | grep -i "xid" | tail -20 || echo "(no Xid errors found)"

check-dmesg:
	@echo "=== Recent GPU/NVIDIA kernel messages ==="
	@sudo dmesg | grep -iE "(nvidia|xid|nvrm|gpu|pci.*10de)" | tail -40 || echo "(no relevant messages)"

watch-dmesg:
	@echo "=== Monitoring dmesg for GPU/NVIDIA messages (Ctrl+C to stop) ==="
	sudo dmesg -wT | grep --line-buffered -iE "(nvidia|xid|nvrm|gpu|pci.*10de)"

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
