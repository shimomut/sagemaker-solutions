# HyperPod Slurm Custom Health Monitoring

This solution demonstrates how to install and run a custom health monitoring service using systemd on HyperPod Slurm clusters. The service continuously monitors worker node health and triggers automatic remediation when issues are detected.

## Overview

The health monitoring service:
- Runs as a systemd service with automatic restart on failure
- Checks if the instance is a worker node (not head node)
- Monitors slurmd daemon health status
- Monitors disk space usage on root filesystem
- Triggers instance reboot via `batch-reboot-cluster-nodes` API for service issues or moderate disk usage
- Triggers instance replacement via `batch-replace-cluster-nodes` API for critical disk space issues
- Logs all activities for troubleshooting

## Prerequisites

### IAM Permissions

The HyperPod cluster's IAM execution role must include permissions to call the remediation APIs. Add the following inline policy to your cluster's IAM role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "sagemaker:BatchRebootClusterNodes",
                "sagemaker:BatchReplaceClusterNodes",
                "sagemaker:DescribeCluster"
            ],
            "Resource": "arn:aws:sagemaker:*:*:cluster/*"
        }
    ]
}
```

For more restrictive permissions, limit to your specific cluster:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "sagemaker:BatchRebootClusterNodes",
                "sagemaker:BatchReplaceClusterNodes",
                "sagemaker:DescribeCluster"
            ],
            "Resource": "arn:aws:sagemaker:us-west-2:123456789012:cluster/abcdefghijkl"
        }
    ]
}
```

**Permissions explained:**
- `sagemaker:BatchRebootClusterNodes` - Required for triggering node reboots (used by this solution)
- `sagemaker:BatchReplaceClusterNodes` - Optional, for future enhancements to replace failed nodes
- `sagemaker:DescribeCluster` - Optional, for retrieving cluster status information

### Required Tools

The following tools must be available on the nodes:
- `ec2-metadata` - For retrieving instance metadata
- `aws` CLI - For calling SageMaker APIs
- `systemctl` - For service management
- `df` - For checking disk space

These are typically pre-installed on HyperPod nodes.

## Components

- `custom-health-monitor.service` - Systemd service definition
- `custom-health-monitor.sh` - Health check script that runs continuously
- `Makefile` - Installation, management, and testing commands

## Installation

### Using Makefile (Recommended)

```bash
# Install and start the service
make install

# Check service status
make status

# View logs
make logs

# Uninstall the service
make uninstall
```

### Manual Installation

```bash
# Copy files
sudo cp custom-health-monitor.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/custom-health-monitor.sh
sudo cp custom-health-monitor.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable custom-health-monitor
sudo systemctl start custom-health-monitor

# Check status
sudo systemctl status custom-health-monitor
```

## Configuration

Edit `custom-health-monitor.sh` to customize:
- `CHECK_INTERVAL` - Time between health checks (default: 60 seconds)
- `DISK_USAGE_REBOOT_THRESHOLD` - Disk usage percentage to trigger reboot (default: 90%)
- `DISK_USAGE_REPLACE_THRESHOLD` - Disk usage percentage to trigger replacement (default: 98%)
- Health check logic and conditions

## Health Checks

The monitor performs the following health checks:

### Service Health (triggers reboot)
- Verifies slurmd daemon is active and running
- Checks systemd service status

### Disk Space Health (triggers reboot or replacement)
The script monitors root filesystem (`/`) disk space usage to prevent node failures:

**Remediation Logic:**
- **90-97% usage** → Trigger reboot (clears temporary files, rotates logs, restarts services)
- **≥98% usage** → Trigger replacement (persistent disk space issue, likely needs investigation)

A reboot often resolves disk space issues by:
- Clearing `/tmp` and other temporary directories
- Rotating and compressing logs
- Releasing deleted but open file handles
- Restarting services that may be holding disk space

If disk usage remains critically high after reboot, replacement allows for manual investigation.

## How It Works

1. Service starts on boot and runs continuously
2. Every `CHECK_INTERVAL` seconds, the script:
   - Checks if running on a worker node (skips head nodes)
   - Verifies slurmd is active and running
   - Checks root filesystem (`/`) disk space usage
   - Triggers instance replacement via `batch-replace-cluster-nodes` API for critical disk issues (≥98%)
   - Triggers instance reboot via `batch-reboot-cluster-nodes` API for service issues or moderate disk usage (90-97%)
3. All actions are logged to systemd journal
4. The script retrieves cluster information from HyperPod metadata:
   - Cluster name from ec2-metadata user-data
   - Region from availability zone
   - Instance ID from ec2-metadata

## Integration with HyperPod Lifecycle Scripts

To deploy this during cluster creation, add to your `on_create.sh`:

```bash
# Install custom health monitoring
cd /tmp
git clone <your-repo>
cd sagemaker-solutions/_experiments/hyperpod_slurm_custom_health_monitoring
make install
```

## Monitoring

```bash
# Check service status
make status

# View recent logs
make logs

# View all logs
sudo journalctl -u custom-health-monitor --no-pager

# Follow logs in real-time
make logs-follow
```

## Testing

The solution includes a test utility to simulate disk space issues:

### Quick Test Commands

```bash
# Fill disk to 92% (triggers reboot threshold)
make test-disk-fill

# Check current disk usage
make test-disk-status

# Clean up test file
make test-disk-cleanup
```

### Manual Testing

```bash
# Fill disk to specific percentage
sudo ./test-disk-fill.sh --target 92   # Triggers reboot
sudo ./test-disk-fill.sh --target 99   # Triggers replacement

# Check status
./test-disk-fill.sh --status

# Clean up
sudo ./test-disk-fill.sh --cleanup
```

### Testing Workflow

1. **Install the health monitor**:
   ```bash
   make install
   ```

2. **Monitor the logs in one terminal**:
   ```bash
   make logs-follow
   ```

3. **Fill disk in another terminal**:
   ```bash
   make test-disk-fill
   ```

4. **Observe the health monitor**:
   - At 90-97% usage: Should trigger reboot
   - At ≥98% usage: Should trigger replacement

5. **Clean up after testing**:
   ```bash
   make test-disk-cleanup
   ```

### Test Utility Features

The `test-disk-fill.sh` script:
- Safely fills disk space in 100MB chunks
- Stops automatically at target percentage
- Includes safety limit at 99% to prevent complete disk fill
- Creates test file at `/tmp/disk-fill-test.bin`
- Automatically cleans up on Ctrl+C or exit
- Shows real-time progress and disk usage

## Troubleshooting

### Service Fails to Start
1. Check service status: `sudo systemctl status custom-health-monitor`
2. View logs: `sudo journalctl -u custom-health-monitor -n 50`
3. Verify script permissions: `ls -l /usr/local/bin/custom-health-monitor.sh`
4. Test script manually: `sudo /usr/local/bin/custom-health-monitor.sh`

### AccessDeniedException Error
If you see an error like:
```
An error occurred (AccessDeniedException) when calling the BatchRebootClusterNodes operation
```

This means the cluster's IAM role lacks the required permissions. Add the `sagemaker:BatchRebootClusterNodes` permission to the IAM role as described in the Prerequisites section.

### Cannot Determine Cluster Name
If the script cannot extract the cluster name from metadata:
1. Verify ec2-metadata is installed: `which ec2-metadata`
2. Check user-data contains CLUSTER_NAME: `ec2-metadata --user-data | grep CLUSTER_NAME`
3. Ensure the node is part of a HyperPod cluster

## Uninstallation

```bash
make uninstall
```

## Notes

- This is a custom health monitor separate from HyperPod's built-in health monitoring
- The service runs with root privileges (required for systemd operations and API calls)
- Automatic restart is configured if the service crashes
- The service is enabled to start on boot
- Reboot actions use the HyperPod `batch-reboot-cluster-nodes` API
