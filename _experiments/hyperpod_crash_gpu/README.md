# GPU Crash Test — HyperPod Resiliency Testing

Intentionally crashes GPU(s) at the driver level to test how HyperPod's resiliency detects and recovers from GPU failures.

## Quick Start

```bash
# Set up the environment and install dependencies
make install          # Creates .venv with Python 3.12 and installs pycuda

# Python version (recommended — no build step)
make crash            # Crash GPU 0

# C/CUDA version (if no Python CUDA library available)
make build            # Compile
make crash-c          # Crash GPU 0
```

## Methods

| Method | Flag | What it does | Reliability |
|--------|------|-------------|-------------|
| **hang** (default) | `--method hang` | Infinite loop saturating all SMs | High — reliably triggers Xid 43/45 |
| **memfault** | `--method memfault` | Illegal memory access at unmapped address | Medium — triggers Xid 31, may escalate to 45 |

The `hang` method is recommended. It launches infinite-loop kernels across all Streaming Multiprocessors, making the GPU completely unresponsive to the driver. On Linux (no TDR by default), this reliably causes the GPU to fall off the PCIe bus.

## Usage

### Python Version

Requires one of: `pycuda`, `cupy`, or `numba`.

```bash
make crash                    # Crash GPU 0 with infinite loop
make crash GPU=1              # Crash GPU 1
make crash-all                # Crash ALL GPUs
make crash-memfault           # Use illegal memory access method
make crash GPU=0 METHOD=hang  # Explicit GPU and method
```

Or directly:

```bash
python3 crash_gpu.py --gpu 0 --method hang
python3 crash_gpu.py --gpu all
python3 crash_gpu.py --gpu 1 --method memfault --delay 10
```

### C/CUDA Version

Requires `nvcc` (CUDA toolkit).

```bash
make build                    # Compile crash_gpu.cu → crash_gpu_c
make crash-c                  # Crash GPU 0
make crash-c GPU=1            # Crash GPU 1
make crash-c GPU=0 METHOD=memfault
```

Or directly:

```bash
./crash_gpu_c 0 hang
./crash_gpu_c 1 memfault
```

## Diagnostics

```bash
make check          # GPU health + recent Xid errors
make check-dmesg    # Recent NVIDIA kernel messages
```

After a crash, you should see:
- `nvidia-smi` hangs or reports the GPU as missing
- `dmesg` shows Xid errors (31, 43, 45)
- HyperPod should detect the failure and initiate recovery

## What to Expect

1. The program asks you to type `CRASH` to confirm
2. Kernel launches across all SMs
3. `cudaDeviceSynchronize()` hangs (for the `hang` method)
4. The GPU becomes unresponsive — `nvidia-smi` will hang or error
5. After some time, the kernel logs Xid errors (`dmesg | grep Xid`)
6. HyperPod's health monitoring should detect the failure

## Recovery

After crashing a GPU, recovery typically requires:
- **Best case**: GPU driver reset (`nvidia-smi -r` if it responds)
- **Typical case**: Full node reboot
- **HyperPod**: The cluster's resiliency should auto-replace the node

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
