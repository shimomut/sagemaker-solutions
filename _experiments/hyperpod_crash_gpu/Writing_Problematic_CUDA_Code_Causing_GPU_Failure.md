# Writing Problematic CUDA Code Causing GPU Failure

## User
*4/29/2026, 4:45:03 PM*

Is it possible to write a problematic CUDA application code to let GPU fail and drop?

---

## Assistant
*4/29/2026, 4:45:03 PM*



That's an interesting question! Yes, it is absolutely possible to write CUDA code that can cause a GPU to fail or become unresponsive. Here are several ways this can happen:

## 1. **Infinite Loops in Kernels**
```cuda
__global__ void hang_kernel() {
    while (true) {} // GPU hangs, triggers TDR timeout
}
```
The GPU will become unresponsive. On Windows, the **TDR (Timeout Detection and Recovery)** mechanism will eventually reset the GPU. On Linux, the behavior depends on the driver and system configuration — it may require a manual reset.

## 2. **Illegal Memory Access (Out-of-Bounds)**
```cuda
__global__ void bad_access_kernel() {
    int *p = (int*)0xDEADBEEF;
    *p = 42; // Illegal memory access
}
```
This triggers a **CUDA error** (`illegal memory access`) and puts the CUDA context into an **unrecoverable error state**. All subsequent CUDA calls will fail.

## 3. **Double-Free / Use-After-Free**
```cuda
int *d_ptr;
cudaMalloc(&d_ptr, 1024);
cudaFree(d_ptr);
cudaFree(d_ptr); // Double free — undefined behavior
```

## 4. **Stack Overflow via Deep Recursion**
```cuda
__device__ int recurse(int n) {
    return recurse(n + 1); // Infinite recursion
}
__global__ void overflow_kernel() {
    recurse(0);
}
```

## 5. **Exhausting GPU Memory**
```cuda
while (cudaMalloc(&ptr, 1GB) == cudaSuccess) {} // OOM
```
Won't "crash" the GPU per se, but can make the system extremely unstable, especially if other processes (including the display server) need GPU memory.

## 6. **Triggering an Xid Error (Hardware-Level Failure)**
Some of the above scenarios can escalate to **Xid errors** logged in the kernel (`dmesg`), such as:
- **Xid 31** – GPU memory page fault
- **Xid 43** – GPU stopped processing
- **Xid 45** – Preemptive cleanup (unrecoverable)
- **Xid 48** – Double bit ECC error

These can cause the GPU to **fall off the PCIe bus** entirely, requiring a full machine reboot to recover.

## What "GPU Drop" Looks Like

When a GPU truly "drops," you'll see:
- `nvidia-smi` hangs or shows the GPU as missing
- `dmesg` logs Xid errors and possibly PCIe errors
- Applications using the GPU get killed or hang
- The GPU is no longer visible to the OS until reboot (or sometimes a PCIe bus reset)

## Key Distinction

| Scenario | Severity | Recovery |
|---|---|---|
| CUDA context error | Low | Restart application |
| TDR / GPU reset | Medium | Automatic (Windows) or manual reset |
| GPU falls off bus | High | Full machine reboot |
| Hardware damage (sustained thermal/power abuse) | Critical | RMA |

## Practical Notes

- On **cloud instances** (like EC2 P4d/P5), a GPU drop typically triggers instance health checks and may result in the instance being retired.
- **ECC errors** (especially uncorrectable ones) can also cause GPUs to drop — this is a hardware issue, not necessarily caused by bad code.
- Tools like `cuda-memcheck` / `compute-sanitizer` can help detect problematic memory access patterns before they escalate.

Would you like me to dive deeper into any specific scenario, like how to intentionally stress-test GPU resilience or how to detect/recover from GPU failures programmatically?

---

## User
*4/29/2026, 4:51:07 PM*

Within the proposed approaches, which are good to let GPU fail at driver or hardware level, not at application level.

---

## Assistant
*4/29/2026, 4:51:07 PM*

Great question — you're distinguishing between a **CUDA runtime/application-level error** (which only kills your app) vs. a **driver or hardware-level failure** (which affects the entire GPU and potentially the system). Here's how the approaches stack up:

## Application-Level Only (❌ Won't cause driver/HW failure)

| Approach | Why it stays at app level |
|---|---|
| **Double-free / Use-after-free** | CUDA runtime catches it; corrupts your context, not the driver |
| **OOM (memory exhaustion)** | `cudaMalloc` returns an error code; driver handles it gracefully |
| **Simple illegal memory access** (within GPU address space) | Triggers Xid 31, but usually just kills the context — driver recovers |

## Can Escalate to Driver/Hardware Level (✅ Good candidates)

### 1. **Infinite Loop in Kernel** ⭐
- If there's **no TDR** (Linux default, or TDR disabled on Windows), the GPU becomes **permanently hung**.
- The driver cannot preempt the kernel on older architectures (pre-Volta compute preemption).
- Result: GPU stops responding, `nvidia-smi` hangs, Xid 43 ("GPU stopped processing") → GPU may **fall off the PCIe bus**.
- **This is the simplest and most reliable way to hang a GPU at the driver level.**

### 2. **Illegal Memory Access (targeting unmapped/MMIO regions)** ⭐
- A *carefully crafted* out-of-bounds access that hits unmapped PCIe BAR regions or triggers a **fatal fault** in the GPU's MMU can cause:
  - **Xid 31** (page fault) escalating to **Xid 45** (preemptive cleanup, unrecoverable)
  - Driver-level reset or GPU drop
- This is less predictable than an infinite loop but can hit harder.

### 3. **Stack Overflow / Infinite Recursion** ⚠️ (sometimes)
- On some GPU architectures/driver versions, a massive stack overflow can corrupt internal GPU state rather than being caught cleanly.
- Less reliable — newer drivers handle this more gracefully.

## Summary: Best Approaches for Driver/HW-Level Failure

| Approach | Reliability | Mechanism | Typical Xid |
|---|---|---|---|
| **Infinite kernel loop** (no TDR) | 🟢 High | GPU hangs, driver times out, can't recover | Xid 43, 45 |
| **Massive concurrent infinite loops** (all SMs busy) | 🟢 Very High | Saturates all compute units, blocks driver commands | Xid 43 |
| **Targeted illegal memory access** | 🟡 Medium | MMU fault → driver reset → possible bus drop | Xid 31 → 45 |
| **Infinite recursion** | 🟠 Low | Stack corruption, architecture-dependent | Varies |

## The Most Effective Pattern

```cuda
// Launch enough threads to saturate ALL SMs
__global__ void kill_gpu() {
    while (true) {
        // Optional: do some math to keep ALUs busy and generate heat
        asm volatile(""); // Prevent compiler from optimizing away
    }
}

int main() {
    // Launch across all SMs with max occupancy
    kill_gpu<<<1024, 1024>>>();
    cudaDeviceSynchronize(); // This call will never return
}
```

**Why this works at the driver level:**
- All Streaming Multiprocessors are occupied
- The driver can't issue management commands to the GPU
- No compute preemption available (or it's overwhelmed)
- The GPU becomes completely unresponsive to the host
- Eventually triggers Xid 43/45 and the GPU may fall off the bus

## Key Factor: TDR / Watchdog

- **Windows**: TDR is ON by default (2-second timeout) → resets the GPU before it truly drops. You'd need to disable TDR to get a real hardware-level hang.
- **Linux**: No TDR by default → infinite loops will reliably hang the GPU at the driver level.

Would you like me to put together a complete test program designed to reliably trigger a GPU drop, or explore recovery mechanisms (like PCIe bus reset)?

---

## User
*4/29/2026, 4:54:12 PM*

Generate a code to try to crash a GPU. This is to check how HyperPod's resiliency handles these cases.

---

## Assistant
*4/29/2026, 4:54:12 PM*

---
