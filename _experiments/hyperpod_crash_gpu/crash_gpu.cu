/**
 * GPU Crash Test — C/CUDA version
 *
 * Launches infinite-loop kernels that saturate all SMs, causing the GPU to
 * become unresponsive at the driver level. On Linux (no TDR by default),
 * this reliably triggers Xid 43/45 and can cause the GPU to fall off the bus.
 *
 * Build:  nvcc -o crash_gpu crash_gpu.cu
 * Usage:  ./crash_gpu [gpu_id] [method]
 *         ./crash_gpu 0 hang       # Infinite loop on GPU 0 (default)
 *         ./crash_gpu 1 memfault   # Illegal memory access on GPU 1
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cuda_runtime.h>

#define CUDA_CHECK(call)                                                       \
    do {                                                                        \
        cudaError_t err = call;                                                 \
        if (err != cudaSuccess) {                                               \
            fprintf(stderr, "CUDA error at %s:%d — %s\n", __FILE__, __LINE__,  \
                    cudaGetErrorString(err));                                    \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

/**
 * Infinite loop kernel — saturates all SMs.
 * asm volatile("") prevents the compiler from optimizing the loop away.
 */
__global__ void hang_kernel() {
    while (true) {
        asm volatile("");
    }
}

/**
 * Illegal memory access kernel — writes to an unmapped address.
 * Triggers a GPU MMU fault (Xid 31) which can escalate to Xid 45.
 */
__global__ void memfault_kernel() {
    int *p = (int *)0xDEADBEEFDEAD0000ULL;
    *p = 0xBADBAD;
}

void print_usage(const char *prog) {
    printf("Usage: %s [gpu_id] [method]\n", prog);
    printf("\n");
    printf("  gpu_id   GPU index (default: 0)\n");
    printf("  method   'hang' (default) or 'memfault'\n");
    printf("\n");
    printf("Examples:\n");
    printf("  %s              # Crash GPU 0 with infinite loop\n", prog);
    printf("  %s 1            # Crash GPU 1 with infinite loop\n", prog);
    printf("  %s 0 memfault   # Crash GPU 0 with illegal memory access\n", prog);
}

int main(int argc, char *argv[]) {
    int gpu_id = 0;
    const char *method = "hang";

    if (argc > 1) {
        if (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0) {
            print_usage(argv[0]);
            return 0;
        }
        gpu_id = atoi(argv[1]);
    }
    if (argc > 2) {
        method = argv[2];
    }

    /* Validate GPU */
    int device_count = 0;
    CUDA_CHECK(cudaGetDeviceCount(&device_count));
    if (device_count == 0) {
        fprintf(stderr, "ERROR: No CUDA-capable GPUs found.\n");
        return 1;
    }
    if (gpu_id < 0 || gpu_id >= device_count) {
        fprintf(stderr, "ERROR: GPU %d not found. Available: 0-%d\n",
                gpu_id, device_count - 1);
        return 1;
    }

    CUDA_CHECK(cudaSetDevice(gpu_id));

    cudaDeviceProp prop;
    CUDA_CHECK(cudaGetDeviceProperties(&prop, gpu_id));

    printf("============================================================\n");
    printf("GPU Crash Test — HyperPod Resiliency Testing (C/CUDA)\n");
    printf("============================================================\n");
    printf("GPU %d: %s\n", gpu_id, prop.name);
    printf("  SMs: %d, Max threads/SM: %d\n",
           prop.multiProcessorCount, prop.maxThreadsPerMultiProcessor);
    printf("  Compute capability: %d.%d\n", prop.major, prop.minor);
    printf("Method: %s\n\n", method);

    printf("⚠️  WARNING: This will make GPU %d UNRESPONSIVE.\n", gpu_id);
    printf("   Recovery typically requires a node reboot.\n\n");
    printf("Type 'CRASH' to proceed: ");
    fflush(stdout);

    char confirm[64] = {0};
    if (fgets(confirm, sizeof(confirm), stdin) == NULL) {
        printf("\nAborted.\n");
        return 0;
    }
    /* Strip newline */
    confirm[strcspn(confirm, "\n")] = 0;

    if (strcmp(confirm, "CRASH") != 0) {
        printf("Aborted.\n");
        return 0;
    }

    /* Calculate launch config to saturate all SMs */
    int blocks = prop.multiProcessorCount * 4;  /* 4x oversubscription */
    int threads = 1024;                          /* max threads per block */

    printf("\nLaunching crash kernel: <<<%d, %d>>> on GPU %d...\n",
           blocks, threads, gpu_id);

    if (strcmp(method, "memfault") == 0) {
        memfault_kernel<<<blocks, threads>>>();
    } else {
        hang_kernel<<<blocks, threads>>>();
    }

    printf("Kernel launched. Synchronizing (will hang for 'hang' method)...\n");
    fflush(stdout);

    cudaError_t err = cudaDeviceSynchronize();
    if (err != cudaSuccess) {
        printf("GPU error (expected): %s\n", cudaGetErrorString(err));
    } else {
        printf("Sync returned (unexpected for hang method).\n");
    }

    return 0;
}
