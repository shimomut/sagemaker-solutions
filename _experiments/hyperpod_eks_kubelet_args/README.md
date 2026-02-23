# HyperPod EKS Kubelet Arguments

Simple solution for configuring kubelet arguments on HyperPod EKS nodes using systemd ExecStart override.

## The Solution

A single script (`configure-kubelet-args.sh`) that overrides the kubelet `ExecStart` command using a systemd drop-in configuration file.

## How It Works

1. Gets the current kubelet `ExecStart` command from systemd
2. Appends additional kubelet arguments to the command
3. Creates `/etc/systemd/system/kubelet.service.d/10-kubelet-args-override.conf`
4. Reloads systemd and restarts kubelet to apply changes

## Usage

### Basic Usage

```bash
# With custom values
./configure-kubelet-args.sh 110 100m 1Gi

# With default values (110 max-pods, 100m CPU, 1Gi memory)
./configure-kubelet-args.sh
```

### HyperPod Lifecycle Integration

Copy the script to your lifecycle script bucket and call it from your `on_create.sh`:

```bash
# In your on_create.sh lifecycle script

# Download from S3 (example)
aws s3 cp s3://your-bucket/lifecycle-scripts/configure-kubelet-args.sh /tmp/
chmod +x /tmp/configure-kubelet-args.sh

# Run with custom values
/tmp/configure-kubelet-args.sh 110 100m 1Gi

# Or with defaults
/tmp/configure-kubelet-args.sh
```

## Verification

Check that kubelet is using the new arguments:

```bash
ps aux | grep kubelet | grep -v grep
```

You should see your additional arguments in the kubelet process command line.

## Parameters

- `max-pods` (default: 110) - Maximum number of pods per node
- `kube-reserved-cpu` (default: 100m) - CPU reserved for Kubernetes system daemons
- `kube-reserved-memory` (default: 1Gi) - Memory reserved for Kubernetes system daemons

Additional arguments automatically included:
- `--system-reserved=cpu=100m,memory=500Mi` - Resources reserved for system daemons
- `--eviction-hard=memory.available<200Mi,nodefs.available<10%` - Hard eviction thresholds

## Notes

- Script must be run as root (use in lifecycle scripts which run as root)
- Uses systemd drop-in configuration at `/etc/systemd/system/kubelet.service.d/10-kubelet-args-override.conf`
- Automatically restarts kubelet to apply changes
- Changes persist across node reboots
- No prompts or interactive input required - suitable for automation
- Always test in non-production environments first

## Cleanup

To remove the configuration:

```bash
sudo rm /etc/systemd/system/kubelet.service.d/10-kubelet-args-override.conf
sudo systemctl daemon-reload
sudo systemctl restart kubelet
```
