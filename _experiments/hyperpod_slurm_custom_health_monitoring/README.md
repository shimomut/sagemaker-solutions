# HyperPod Slurm Custom Health Monitoring

This solution demonstrates how to install and run a custom health monitoring service using systemd on HyperPod Slurm clusters. The service continuously monitors worker node health and triggers automatic remediation when issues are detected.

## Overview

The health monitoring service:
- Runs as a systemd service with automatic restart on failure
- Checks if the instance is a worker node (not head node)
- Monitors slurmd daemon health status
- Triggers instance reboot via `batch-reboot-cluster-nodes` API when unhealthy
- Logs all activities for troubleshooting

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
- `SLURMD_RESTART_ATTEMPTS` - Number of restart attempts before reboot (default: 3)
- Health check logic and conditions

## How It Works

1. Service starts on boot and runs continuously
2. Every `CHECK_INTERVAL` seconds, the script:
   - Checks if running on a worker node
   - Verifies slurmd is active and running
   - Attempts to restart slurmd if unhealthy
   - Triggers cluster node reboot if restart fails
3. All actions are logged to systemd journal

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

If the service fails to start:
1. Check service status: `sudo systemctl status custom-health-monitor`
2. View logs: `sudo journalctl -u custom-health-monitor -n 50`
3. Verify script permissions: `ls -l /usr/local/bin/custom-health-monitor.sh`
4. Test script manually: `sudo /usr/local/bin/custom-health-monitor.sh`

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
