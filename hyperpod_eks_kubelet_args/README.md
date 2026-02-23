# HyperPod EKS Kubelet Arguments

Simple solution for configuring kubelet arguments on HyperPod EKS nodes using systemd configuration.

## The Solution

A single script (`configure-kubelet-args.sh`) that configures additional kubelet arguments by:
1. Creating a systemd drop-in file with a new environment variable (`HYPERPOD_KUBELET_ARGS`)
2. Modifying the kubelet service file to append this variable to the ExecStart command

## How It Works

1. Creates `/etc/systemd/system/kubelet.service.d/10-kubelet-args-override.conf` with environment variable
2. Modifies `/etc/systemd/system/kubelet.service` to append `$HYPERPOD_KUBELET_ARGS` to the ExecStart command
3. Reloads systemd daemon to pick up changes
4. HyperPod starts kubelet with the additional arguments during node initialization

## Usage

### Basic Usage

```bash
# With custom values
./configure-kubelet-args.sh 110 100m 1Gi

# With default values (110 max-pods, 100m CPU, 1Gi memory)
./configure-kubelet-args.sh
```

### HyperPod Lifecycle Integration

Copy the script to your lifecycle script bucket and call it from your `on_create.sh` or `on_create_main.sh`:

```bash
# In your lifecycle script (on_create.sh or on_create_main.sh)

# If script is in the same directory
bash ./configure-kubelet-args.sh

# Or with custom values
bash ./configure-kubelet-args.sh 110 100m 1Gi
```

Note: The script should be called during the lifecycle script execution. It configures kubelet before HyperPod starts it, so no restart is needed.

### Sample Lifecycle Scripts

This solution includes sample lifecycle scripts (`on_create.sh` and `on_create_main.sh`) that demonstrate:
- How to invoke `configure-kubelet-args.sh` in your lifecycle script
- Additional HyperPod node configuration (containerd/kubelet disk setup, EFA FSx client setup)

These are reference implementations showing best practices for HyperPod EKS node initialization. You can use them as-is or adapt them to your specific requirements.

## Verification

### On the Node (via SSM)

Check that kubelet is using the new arguments:

```bash
ps aux | grep kubelet | grep -v grep
```

You should see your additional arguments in the kubelet process command line, for example:
```
/usr/bin/kubelet ... --max-pods=110 --kube-reserved=cpu=100m,memory=1Gi --system-reserved=cpu=100m,memory=500Mi --eviction-hard=memory.available<200Mi,nodefs.available<10%
```

### Using kubectl

Verify the configuration from your local machine or head node:

```bash
# Get node name
kubectl get nodes

# Check max pods capacity
kubectl get node <node-name> -o jsonpath='{.status.capacity.pods}' && echo
# Expected: 110

# Check allocatable resources (affected by kube-reserved and system-reserved)
kubectl describe node <node-name> | grep -A 10 "Allocatable:"

# View full node details
kubectl describe node <node-name>
```

Expected results for an ml.m5.xlarge instance (4 CPU, ~16Gi memory):
- **Max Pods**: 110 (instead of default ~29)
- **Allocatable CPU**: ~3800m (4000m - 100m kube-reserved - 100m system-reserved)
- **Allocatable Memory**: ~14.1Gi (16Gi - 1Gi kube-reserved - 500Mi system-reserved - eviction threshold)

Example output:
```
Capacity:
  cpu:                4
  memory:             16170100Ki
  pods:               110
Allocatable:
  cpu:                3800m
  memory:             14404724Ki
  pods:               110
```

## Parameters

- `max-pods` (default: 110) - Maximum number of pods per node
- `kube-reserved-cpu` (default: 100m) - CPU reserved for Kubernetes system daemons
- `kube-reserved-memory` (default: 1Gi) - Memory reserved for Kubernetes system daemons

Additional arguments automatically included:
- `--system-reserved=cpu=100m,memory=500Mi` - Resources reserved for system daemons
- `--eviction-hard=memory.available<200Mi,nodefs.available<10%` - Hard eviction thresholds

## Notes

- Script must be run as root (lifecycle scripts run as root automatically)
- Creates systemd drop-in at `/etc/systemd/system/kubelet.service.d/10-kubelet-args-override.conf`
- Modifies `/etc/systemd/system/kubelet.service` to append `$HYPERPOD_KUBELET_ARGS`
- No kubelet restart needed when run in lifecycle scripts (kubelet hasn't started yet)
- Changes persist across node reboots
- No prompts or interactive input required - suitable for automation
- Always test in non-production environments first
