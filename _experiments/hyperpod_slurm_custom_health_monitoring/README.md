# HyperPod Slurm Custom Health Monitoring

This solution demonstrates how to install and run a custom health monitoring service using systemd on HyperPod Slurm clusters. The service continuously monitors worker node health and triggers automatic remediation when issues are detected.

## Overview

The health monitoring service:
- Runs as a systemd service with automatic restart on failure
- Checks if the instance is a worker node (not head node)
- Monitors slurmd daemon health status
- Triggers instance reboot via `batch-reboot-cluster-nodes` API when unhealthy
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
            "Resource": "arn:aws:sagemaker:us-west-2:842413447717:cluster/onhwgliuxn4u"
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
- `jq` - For JSON parsing (if using resource config fallback)

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
- Health check logic and conditions

## How It Works

1. Service starts on boot and runs continuously
2. Every `CHECK_INTERVAL` seconds, the script:
   - Checks if running on a worker node (skips head nodes)
   - Verifies slurmd is active and running
   - Triggers cluster node reboot via `batch-reboot-cluster-nodes` API if unhealthy
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
sudo journalctl -u health-monitor --no-pager

# Follow logs in real-time
sudo journalctl -u health-monitor -f
```

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
