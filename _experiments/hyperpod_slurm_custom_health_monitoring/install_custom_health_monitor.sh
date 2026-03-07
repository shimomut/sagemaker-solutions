#!/bin/bash

# Installation script for HyperPod Slurm Custom Health Monitor
# This script can be called from Makefiles or HyperPod lifecycle scripts

set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

log "Installing HyperPod Slurm Custom Health Monitor..."

# Check if source files exist
if [ ! -f "$SCRIPT_DIR/custom-health-monitor.sh" ]; then
    echo "ERROR: custom-health-monitor.sh not found in $SCRIPT_DIR"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/custom-health-monitor.service" ]; then
    echo "ERROR: custom-health-monitor.service not found in $SCRIPT_DIR"
    exit 1
fi

# Install the monitoring script
log "Installing script to $INSTALL_PATH..."
cp "$SCRIPT_DIR/custom-health-monitor.sh" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"

# Install the systemd service
log "Installing systemd service..."
cp "$SCRIPT_DIR/custom-health-monitor.service" "$SERVICE_PATH"
chmod 644 "$SERVICE_PATH"

# Reload systemd daemon
log "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service to start on boot
log "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

# Start the service now
log "Starting service..."
systemctl start "$SERVICE_NAME"

# Wait a moment for service to start
sleep 2

# Check service status
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Service started successfully!"
else
    echo "WARNING: Service may not have started. Check logs with: journalctl -u $SERVICE_NAME -n 50"
fi

echo ""
log "=== Installation Complete ==="
log "Service: $SERVICE_NAME"
log "Script: $INSTALL_PATH"
log "Service file: $SERVICE_PATH"
log "Status: Enabled and started"
echo ""
log "To view logs: journalctl -u $SERVICE_NAME -f"
log "To check status: systemctl status $SERVICE_NAME"
echo ""
