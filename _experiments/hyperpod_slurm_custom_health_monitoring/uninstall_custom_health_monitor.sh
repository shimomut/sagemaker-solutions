#!/bin/bash

# Uninstallation script for HyperPod Slurm Custom Health Monitor
# This script can be called from Makefiles or manually

set -euo pipefail

# Configuration
SERVICE_NAME="custom-health-monitor"
INSTALL_PATH="/usr/local/bin/custom-health-monitor.sh"
SERVICE_PATH="/etc/systemd/system/custom-health-monitor.service"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

log "Uninstalling HyperPod Slurm Custom Health Monitor..."

# Stop the service
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    log "Stopping service..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || echo "WARNING: Failed to stop service"
else
    log "Service is not running"
fi

# Disable the service
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    log "Disabling service..."
    systemctl disable "$SERVICE_NAME" 2>/dev/null || echo "WARNING: Failed to disable service"
else
    log "Service is not enabled"
fi

# Remove systemd service file
if [ -f "$SERVICE_PATH" ]; then
    log "Removing systemd service file..."
    rm -f "$SERVICE_PATH"
else
    log "Service file not found (already removed)"
fi

# Remove the monitoring script
if [ -f "$INSTALL_PATH" ]; then
    log "Removing monitoring script..."
    rm -f "$INSTALL_PATH"
else
    log "Monitoring script not found (already removed)"
fi

# Reload systemd daemon
log "Reloading systemd daemon..."
systemctl daemon-reload

echo ""
log "=== Uninstallation Complete ==="
log "The $SERVICE_NAME service has been removed."
echo ""
