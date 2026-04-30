#!/usr/bin/env python3
"""
GPU Crash Test for HyperPod Resiliency Testing

Launches infinite-loop CUDA kernels that saturate all Streaming Multiprocessors,
causing the GPU to become unresponsive at the driver level. On Linux (no TDR),
this reliably triggers Xid 43/45 errors and can cause the GPU to fall off the
PCIe bus — exactly the scenario HyperPod's resiliency should detect and recover.

Usage:
    python3 crash_gpu.py                  # Crash GPU 0
    python3 crash_gpu.py --gpu 1          # Crash GPU 1
    python3 crash_gpu.py --gpu all        # Crash ALL GPUs (nuclear option)
    python3 crash_gpu.py --method hang    # Infinite loop (default, most reliable)
    python3 crash_gpu.py --method memfault # Illegal memory access

WARNING: This WILL make the GPU unresponsive. Recovery requires at minimum
         a GPU reset, and often a full node reboot.
"""

import argparse
import ctypes
import os
import signal
import subprocess
import sys
import time


def check_nvidia_smi():
    """Verify nvidia-smi works and return GPU count."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,uuid", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f"ERROR: nvidia-smi failed: {result.stderr.strip()}")
            sys.exit(1)
        gpus = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return gpus
    except FileNotFoundError:
        print("ERROR: nvidia-smi not found. Are NVIDIA drivers installed?")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: nvidia-smi timed out — GPU may already be in a bad state.")
        sys.exit(1)


def crash_gpu_cuda_python(gpu_id: int, method: str):
    """
    Crash a GPU using CUDA Python (pycuda or cupy).
    Falls back to the compiled C approach if neither is available.
    """
    # Try pycuda first
    try:
        import pycuda.driver as cuda
        import pycuda.autoinit  # noqa: F401
        from pycuda.compiler import SourceModule
        return _crash_with_pycuda(gpu_id, method)
    except ImportError:
        pass

    # Try cupy
    try:
        import cupy
        return _crash_with_cupy(gpu_id, method)
    except ImportError:
        pass

    # Try numba
    try:
        from numba import cuda as numba_cuda
        return _crash_with_numba(gpu_id, method)
    except ImportError:
        pass

    print("ERROR: No CUDA Python library found (pycuda, cupy, or numba).")
    print("       Install one of them, or use the compiled C version instead:")
    print("         pip install pycuda    # or: pip install cupy-cuda12x  /  pip install numba")
    print("         make build            # to build the C version")
    print("         make crash-c          # to run the C version")
    sys.exit(1)


def _crash_with_pycuda(gpu_id: int, method: str):
    """Crash GPU using PyCUDA."""
    import pycuda.driver as cuda

    cuda.init()
    if gpu_id >= cuda.Device.count():
        print(f"ERROR: GPU {gpu_id} not found. Available: 0-{cuda.Device.count()-1}")
        sys.exit(1)

    dev = cuda.Device(gpu_id)
    ctx = dev.make_context()

    from pycuda.compiler import SourceModule

    if method == "hang":
        mod = SourceModule("""
        __global__ void crash_kernel() {
            // Infinite loop — saturates all SMs, hangs the GPU at driver level.
            // asm volatile prevents the compiler from optimizing this away.
            while (true) {
                asm volatile("");
            }
        }
        """)
    else:  # memfault
        mod = SourceModule("""
        __global__ void crash_kernel() {
            // Write to an unmapped address to trigger a fatal GPU MMU fault.
            // This causes Xid 31 (page fault) which can escalate to Xid 45.
            int *p = (int*)0xDEADBEEFDEAD0000ULL;
            *p = 0xBADBAD;
        }
        """)

    crash_kernel = mod.get_function("crash_kernel")

    print(f"[GPU {gpu_id}] Launching crash kernel (method={method})...")
    print(f"[GPU {gpu_id}] The GPU will become unresponsive. This is expected.")

    # Launch with enough blocks/threads to saturate all SMs
    crash_kernel(block=(1024, 1, 1), grid=(1024, 1))

    if method == "hang":
        print(f"[GPU {gpu_id}] Waiting for device sync (this will hang)...")
        try:
            ctx.synchronize()
        except Exception as e:
            print(f"[GPU {gpu_id}] GPU error (expected): {e}")
    else:
        try:
            ctx.synchronize()
        except Exception as e:
            print(f"[GPU {gpu_id}] GPU fault triggered (expected): {e}")

    # We likely never reach here for the hang method
    ctx.pop()


def _crash_with_cupy(gpu_id: int, method: str):
    """Crash GPU using CuPy with raw CUDA kernel."""
    import cupy

    cupy.cuda.Device(gpu_id).use()
    dev_name = cupy.cuda.runtime.getDeviceProperties(gpu_id)["name"]
    print(f"[GPU {gpu_id}] Using CuPy on {dev_name}")

    if method == "hang":
        kernel_code = r"""
        extern "C" __global__ void crash_kernel() {
            while (true) {
                asm volatile("");
            }
        }
        """
    else:
        kernel_code = r"""
        extern "C" __global__ void crash_kernel() {
            int *p = (int*)0xDEADBEEFDEAD0000ULL;
            *p = 0xBADBAD;
        }
        """

    mod = cupy.RawModule(code=kernel_code)
    crash_kernel = mod.get_function("crash_kernel")

    print(f"[GPU {gpu_id}] Launching crash kernel (method={method})...")
    crash_kernel((1024,), (1024,))

    print(f"[GPU {gpu_id}] Synchronizing (will hang for 'hang' method)...")
    try:
        cupy.cuda.Device(gpu_id).synchronize()
    except Exception as e:
        print(f"[GPU {gpu_id}] GPU error (expected): {e}")


def _crash_with_numba(gpu_id: int, method: str):
    """Crash GPU using Numba CUDA. Only supports the hang method."""
    from numba import cuda as numba_cuda

    if method != "hang":
        print("WARNING: Numba only supports the 'hang' method. Switching to hang.")

    numba_cuda.select_device(gpu_id)

    @numba_cuda.jit
    def crash_kernel():
        # Tight infinite loop. Numba doesn't support inline asm, but the
        # loop itself is enough to hang the GPU.
        while True:
            pass

    print(f"[GPU {gpu_id}] Launching crash kernel via Numba (method=hang)...")
    crash_kernel[1024, 1024]()

    print(f"[GPU {gpu_id}] Synchronizing (will hang)...")
    try:
        numba_cuda.synchronize()
    except Exception as e:
        print(f"[GPU {gpu_id}] GPU error (expected): {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Crash GPU(s) for HyperPod resiliency testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 crash_gpu.py                  # Crash GPU 0 with infinite loop
  python3 crash_gpu.py --gpu 1          # Crash GPU 1
  python3 crash_gpu.py --gpu all        # Crash ALL GPUs
  python3 crash_gpu.py --method memfault # Use illegal memory access method

Methods:
  hang      Infinite loop saturating all SMs (most reliable, default)
  memfault  Illegal memory access triggering MMU fault
        """
    )
    parser.add_argument(
        "--gpu", default="0",
        help="GPU index to crash, or 'all' for all GPUs (default: 0)"
    )
    parser.add_argument(
        "--method", choices=["hang", "memfault"], default="hang",
        help="Crash method (default: hang)"
    )
    parser.add_argument(
        "--delay", type=int, default=0,
        help="Delay in seconds before crashing (default: 0)"
    )
    args = parser.parse_args()

    # Show GPU info
    gpus = check_nvidia_smi()
    print("=" * 60)
    print("GPU Crash Test — HyperPod Resiliency Testing")
    print("=" * 60)
    print(f"Detected {len(gpus)} GPU(s):")
    for gpu in gpus:
        print(f"  {gpu}")
    print()

    # Determine target GPUs
    if args.gpu.lower() == "all":
        target_gpus = list(range(len(gpus)))
    else:
        try:
            target_gpus = [int(args.gpu)]
        except ValueError:
            print(f"ERROR: Invalid GPU index: {args.gpu}")
            sys.exit(1)

    print(f"Target GPU(s): {target_gpus}")
    print(f"Method: {args.method}")
    print()

    # Safety confirmation
    print("⚠️  WARNING: This will make the target GPU(s) UNRESPONSIVE.")
    print("   Recovery typically requires a node reboot.")
    print()
    try:
        confirm = input("Type 'CRASH' to proceed: ")
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if confirm != "CRASH":
        print("Aborted.")
        sys.exit(0)

    if args.delay > 0:
        print(f"\nWaiting {args.delay} seconds before crashing...")
        time.sleep(args.delay)

    # For multiple GPUs, fork child processes
    if len(target_gpus) > 1:
        children = []
        for gpu_id in target_gpus:
            pid = os.fork()
            if pid == 0:
                # Child process — crash this GPU
                crash_gpu_cuda_python(gpu_id, args.method)
                os._exit(0)
            else:
                children.append(pid)
                print(f"Forked PID {pid} for GPU {gpu_id}")

        # Parent waits (will likely hang since children hang)
        print("\nAll crash processes launched. Waiting (this will hang)...")
        for pid in children:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
    else:
        crash_gpu_cuda_python(target_gpus[0], args.method)


if __name__ == "__main__":
    main()
