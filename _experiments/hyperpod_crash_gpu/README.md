# GPU Crash Test — HyperPod Resiliency Testing

Intentionally crashes GPU(s) to test how HyperPod's resiliency detects and recovers from GPU failures. Provides both software-level (CUDA kernel) and hardware-level (PCIe/driver) methods.

## Quick Start

```bash
# Set up the environment and install dependencies
make install          # Creates .venv with Python 3.12 and installs pycuda

# Software-level crash (CUDA kernel fault)
make crash-memfault   # Triggers Xid 13/43 — driver recovers automatically

# Hardware-level crash (simulates real GPU failure)
make pci-remove       # Removes GPU from PCIe bus — requires reboot to recover
```

## Methods

There are two categories of crash methods: software-level (CUDA kernel) and hardware-level (PCIe/driver).

### Software-Level (CUDA Kernel)

These launch CUDA kernels that cause GPU faults. The driver detects the fault and kills the offending context, but the GPU itself recovers and remains usable.

| Method | Make target | Xid errors | GPU recovers? |
|--------|------------|------------|---------------|
| **hang** | `make crash` | None — GPU stays busy but driver sees no fault | Yes (kill the process) |
| **memfault** | `make crash-memfault` | Xid 13 (out of range address), Xid 43 (context killed) | Yes (automatically) |

The `memfault` method is more useful for testing — it generates real Xid errors that monitoring tools can detect. The `hang` method saturates all SMs but modern drivers on Linux (no TDR) don't treat it as a fault.

### Hardware-Level (PCIe/Driver)

These simulate real hardware failures at the driver or bus level. They require `sudo` and cause the GPU to become genuinely unavailable to the system.

| Method | Make target | What happens | Recovery |
|--------|------------|-------------|----------|
| **drain** | `make drain` | Marks GPU as unusable via nvidia-smi | `make undrain` |
| **pci-remove** | `make pci-remove` | Removes GPU from PCIe bus entirely | Reboot (see below) |

The `pci-remove` method is the closest simulation to a real hardware failure. The GPU disappears from `nvidia-smi` and `lspci` as if it physically fell off the bus. This is the recommended method for testing HyperPod resiliency.

## Usage

### Software-Level Crashes

```bash
# CUDA kernel faults (Python)
make crash                    # Infinite loop on GPU 0 (no Xid errors)
make crash GPU=1              # Target GPU 1
make crash-all                # Crash ALL GPUs
make crash-memfault           # Illegal memory access — triggers Xid 13/43
make crash GPU=0 METHOD=hang  # Explicit GPU and method

# CUDA kernel faults (C version, no Python needed)
make build                    # Compile crash_gpu.cu → crash_gpu_c
make crash-c                  # Crash GPU 0
make crash-c GPU=1            # Crash GPU 1
```

### Hardware-Level Crashes

All hardware-level targets accept `GPU=N` (default: 0).

```bash
# Drain — marks GPU unusable, blocks new workloads
make drain                    # Drain GPU 0
make drain GPU=1              # Drain GPU 1
make undrain                  # Undo drain, re-enable persistence mode

# PCIe remove — GPU disappears from the system entirely
make pci-remove               # Remove GPU 0 from PCIe bus
make pci-remove GPU=1         # Remove GPU 1

# Recovery
make pci-rescan               # Rescan PCIe bus + rebind driver
make recover                  # Full recovery: undrain + rescan + rebind + persistence mode
```

## Diagnostics

```bash
make check          # GPU health + recent Xid errors
make check-dmesg    # Recent NVIDIA kernel messages
make watch-dmesg    # Follow dmesg live for GPU messages (Ctrl+C to stop)
```

After a crash, you should see:
- Software-level: `dmesg` shows Xid errors (13, 43), GPU remains usable
- Hardware-level: `nvidia-smi` reports "No devices were found"
- HyperPod should detect the failure and initiate recovery

## What to Expect

### Software-Level (memfault)

1. The program asks you to type `CRASH` to confirm
2. Kernel launches across all SMs with an illegal memory access
3. Driver detects the fault and kills the CUDA context
4. Xid 13 and Xid 43 appear in `dmesg`
5. GPU recovers automatically — still visible in `nvidia-smi`

### Hardware-Level (pci-remove)

1. GPU is removed from the PCIe bus
2. `nvidia-smi` shows "No devices were found"
3. `lspci` no longer lists the GPU
4. HyperPod's health monitoring should detect the missing GPU
5. Recovery requires a node reboot (PCIe rescan alone may not rebind the driver)

## Recovery

### From software-level crashes

The GPU recovers automatically after the CUDA context is killed. No action needed — just kill the crash process if it's still running.

### From `make drain`

```bash
make undrain          # Clears drain state and re-enables persistence mode
```

### From `make pci-remove`

The PCIe rescan + driver rebind may work in some cases:

```bash
make recover          # Attempts: undrain + PCIe rescan + driver rebind
```

However, in practice the NVIDIA driver often fails to rebind after a PCIe remove because kernel modules retain stale references. **A node reboot is typically required** — which is exactly the scenario HyperPod's resiliency is designed to handle.

## Prerequisites

### Python version

Set up the virtual environment and install dependencies:

```bash
make venv             # Create .venv with Python 3.12 and upgrade pip
make install          # Create .venv (if needed) and install pycuda
```

`make install` depends on `make venv`, so running `make install` alone is sufficient. All Python make targets (`crash`, `crash-all`, `crash-memfault`) use `.venv/bin/python` by default. You can override this with:

```bash
make crash PYTHON=/usr/bin/python3
```

Alternatively, install a CUDA library manually into the venv:

```bash
source .venv/bin/activate
pip install pycuda
# or
pip install cupy-cuda12x   # match your CUDA version
# or
pip install numba
```

### C version

```bash
# CUDA toolkit with nvcc
which nvcc
```
