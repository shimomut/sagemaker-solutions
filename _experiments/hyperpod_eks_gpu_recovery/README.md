# HyperPod EKS GPU Recovery

This experiment tests whether NVIDIA's GPU device plugin and GPU operator automatically recover GPUs that transition from unhealthy back to healthy, or if a restart is required.

## Background

[GitHub Issue #1014](https://github.com/NVIDIA/k8s-device-plugin/issues/1014) reports that the NVIDIA GPU Device Plugin does not mark devices as healthy again once they have been marked unhealthy — a device plugin restart is required to recover.

This experiment reproduces the issue using DCGM error injection on a HyperPod EKS cluster, then tests recovery behavior under two configurations:

1. **Standalone GPU Device Plugin** (`k8s-device-plugin` DaemonSet)
2. **NVIDIA GPU Operator** (manages device plugin, DCGM, driver, etc.)

## Why Xid 94?

We use **Xid 94 (`ROBUST_CHANNEL_CONTAINED_ERROR`)** for error injection because:

- The NVIDIA device plugin treats Xid 94 as a critical error and marks the GPU unhealthy ([confirmed in issue #1014](https://github.com/NVIDIA/k8s-device-plugin/issues/1014))
- Xid 94 is a "contained" ECC error — it only affects the running application, not the whole GPU. NVIDIA's recommended resolution is "RESTART_APP", not "RESET_GPU"
- **HyperPod's Health Monitoring Agent (HMA) does not trigger node reboot/replace for Xid 94**, since it's an application-level contained error, not a hardware-fatal XID like Xid 71 (NVLink fatal). This means HMA won't race us during testing
- Can be injected and cleared via DCGM field ID 230 (`DCGM_FI_DEV_XID_ERRORS`)

### Why not ECC DBE (field 319)?

Injecting `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` (double-bit ECC errors) would also trigger the device plugin, but it falls under DCGM's "ECC Errors - Fatal" policy category. HMA monitors DCGM policy violations and would likely trigger a node reboot/replace before we can test the clear-and-recover flow.

## Test Plan

### Phase 1: Standalone GPU Device Plugin

1. Verify GPU is healthy and schedulable (`make check-allocatable`)
2. Inject Xid 94 via DCGM (`make inject-error`)
3. Confirm the device plugin marks the GPU unhealthy (`make check-plugin-logs`)
4. Confirm allocatable GPU count drops (`make check-allocatable`)
5. Clear the injected error (`make clear-error`)
6. Wait and observe whether the GPU returns to healthy **without** restarting the device plugin
7. If not, restart the device plugin pod (`make restart-plugin`) and confirm recovery

### Phase 2: NVIDIA GPU Operator

1. Install GPU Operator (`make install-operator`) — replaces standalone device plugin
2. Repeat steps 1-7 from Phase 1
3. Compare recovery behavior

## Prerequisites

- HyperPod EKS cluster with GPU nodes (A100+ for Xid 94 support — p4d, p5, etc.)
- `kubectl` configured for the cluster
- DCGM installed on GPU nodes (included in NVIDIA driver containers)
- Sufficient permissions to exec into DaemonSet pods

## Error Injection Method

Uses [NVIDIA DCGM Error Injection](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-error-injection.html) to simulate Xid 94 (contained ECC error) without causing real hardware faults.

```bash
# Inject Xid 94 on GPU 0
dcgmi test --inject --gpuid 0 -f 230 -v 94

# Check GPU health
dcgmi health -g 0 -c

# Clear the injected error (inject Xid value 0)
dcgmi test --inject --gpuid 0 -f 230 -v 0
```

Field ID 230 = `DCGM_FI_DEV_XID_ERRORS` (XID error field, value = specific XID number).

> **Note**: Xid 94 (`ROBUST_CHANNEL_CONTAINED_ERROR`) is supported on Ampere (A100) and newer GPUs with CUDA 12.7+ / driver R565+. See [NVIDIA Xid Catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html).

## Usage

```bash
# Show available commands
make help

# --- Pre-checks ---
make check-nodes          # List GPU nodes and allocatable GPUs
make check-plugin-pods    # List device plugin pods
make check-gpu-health     # Check DCGM health on a node
make check-allocatable    # Show allocatable/capacity GPU counts
make check-plugin-logs    # Tail device plugin logs for XID events

# --- Phase 1: Standalone Device Plugin ---
make inject-error         # Inject Xid 94 via DCGM
make check-plugin-logs    # Verify device plugin detected the error
make check-allocatable    # Confirm GPU count dropped
make clear-error          # Clear the injected error
make check-allocatable    # Check if GPU recovers automatically
make restart-plugin       # Restart device plugin pod (if recovery fails)

# --- Phase 2: GPU Operator ---
make install-operator     # Install NVIDIA GPU Operator via Helm
make uninstall-operator   # Uninstall GPU Operator

# --- Test Workload ---
make deploy-test-pod      # Deploy a GPU pod (tests schedulability)
make delete-test-pod      # Delete the test pod

# --- Cleanup ---
make cleanup              # Remove test resources
```

## Key Observations to Record

| Scenario | GPU Marked Unhealthy? | Auto-Recovery After Clear? | Recovery After Plugin Restart? | HMA Triggered? |
|---|---|---|---|---|
| Standalone Device Plugin | | | | |
| GPU Operator | | | | |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GPU_NODE` | *(first GPU node)* | Target node for error injection |
| `GPU_ID` | `0` | GPU index to inject error on |
| `NAMESPACE` | `kube-system` | Namespace of device plugin pods |
| `OPERATOR_NAMESPACE` | `gpu-operator` | Namespace for GPU Operator |
| `XID_VALUE` | `94` | XID error code to inject |

## References

- [NVIDIA k8s-device-plugin Issue #1014](https://github.com/NVIDIA/k8s-device-plugin/issues/1014) — GPU not recovered after XID clears
- [DCGM Error Injection Guide](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-error-injection.html)
- [DCGM Field Identifiers (dcgm_fields.h)](https://github.com/NVIDIA/DCGM/blob/master/dcgmlib/dcgm_fields.h) — Field 230 = `DCGM_FI_DEV_XID_ERRORS`
- [NVIDIA Xid Error Catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html) — Xid 94 = Contained ECC error
- [NVIDIA GPU Operator Docs](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html)
- [HyperPod Health Monitoring System](https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-eks-resiliency-health-monitoring-agent.html)
