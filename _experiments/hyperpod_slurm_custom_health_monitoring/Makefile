.PHONY: help install uninstall status logs logs-all logs-follow restart stop start enable disable test-script

help:
	@echo "HyperPod Slurm Custom Health Monitoring - Makefile Commands"
	@echo ""
	@echo "Installation & Management:"
	@echo "  make install        - Install and start the health monitoring service"
	@echo "  make uninstall      - Stop and remove the health monitoring service"
	@echo ""
	@echo "Service Control:"
	@echo "  make start          - Start the service"
	@echo "  make stop           - Stop the service"
	@echo "  make restart        - Restart the service"
	@echo "  make enable         - Enable service to start on boot"
	@echo "  make disable        - Disable service from starting on boot"
	@echo ""
	@echo "Monitoring:"
	@echo "  make status         - Check service status"
	@echo "  make logs           - View recent logs (last 50 lines)"
	@echo "  make logs-all       - View all logs"
	@echo "  make logs-follow    - Follow logs in real-time"
	@echo ""
	@echo "Testing:"
	@echo "  make test-script    - Test the health monitor script manually"

install:
	@echo "Installing HyperPod Slurm Custom Health Monitor..."
	@echo "Installing script to /usr/local/bin/custom-health-monitor.sh..."
	@sudo cp custom-health-monitor.sh /usr/local/bin/custom-health-monitor.sh
	@sudo chmod +x /usr/local/bin/custom-health-monitor.sh
	@echo "Installing systemd service..."
	@sudo cp custom-health-monitor.service /etc/systemd/system/custom-health-monitor.service
	@sudo chmod 644 /etc/systemd/system/custom-health-monitor.service
	@echo "Reloading systemd daemon..."
	@sudo systemctl daemon-reload
	@echo "Enabling service to start on boot..."
	@sudo systemctl enable custom-health-monitor
	@echo "Starting service..."
	@sudo systemctl start custom-health-monitor
	@echo ""
	@echo "Installation complete!"
	@echo ""
	@echo "Service status:"
	@sudo systemctl status custom-health-monitor --no-pager || true
	@echo ""
	@echo "To view logs: make logs-follow"
	@echo "To check status: make status"

uninstall:
	@echo "Uninstalling HyperPod Slurm Custom Health Monitor..."
	@echo "Stopping service..."
	@sudo systemctl stop custom-health-monitor 2>/dev/null || true
	@echo "Disabling service..."
	@sudo systemctl disable custom-health-monitor 2>/dev/null || true
	@echo "Removing systemd service file..."
	@sudo rm -f /etc/systemd/system/custom-health-monitor.service
	@echo "Removing script..."
	@sudo rm -f /usr/local/bin/custom-health-monitor.sh
	@echo "Reloading systemd daemon..."
	@sudo systemctl daemon-reload
	@echo ""
	@echo "Uninstallation complete!"
	@echo "The custom-health-monitor service has been removed."

status:
	@echo "Checking service status..."
	@sudo systemctl status custom-health-monitor --no-pager || true

logs:
	@echo "Viewing recent logs (last 50 lines)..."
	@sudo journalctl -u custom-health-monitor -n 50 --no-pager

logs-all:
	@echo "Viewing all logs..."
	@sudo journalctl -u custom-health-monitor --no-pager

logs-follow:
	@echo "Following logs in real-time (Ctrl+C to exit)..."
	@sudo journalctl -u custom-health-monitor -f

restart:
	@echo "Restarting service..."
	@sudo systemctl restart custom-health-monitor
	@echo "Service restarted. Checking status..."
	@sleep 2
	@sudo systemctl status custom-health-monitor --no-pager || true

stop:
	@echo "Stopping service..."
	@sudo systemctl stop custom-health-monitor
	@echo "Service stopped."

start:
	@echo "Starting service..."
	@sudo systemctl start custom-health-monitor
	@echo "Service started. Checking status..."
	@sleep 2
	@sudo systemctl status custom-health-monitor --no-pager || true

enable:
	@echo "Enabling service to start on boot..."
	@sudo systemctl enable custom-health-monitor
	@echo "Service enabled."

disable:
	@echo "Disabling service from starting on boot..."
	@sudo systemctl disable custom-health-monitor
	@echo "Service disabled."

test-script:
	@echo "Testing health monitor script manually..."
	@echo "Note: This will run the script in foreground. Press Ctrl+C to stop."
	@echo ""
	@chmod +x custom-health-monitor.sh
	@sudo ./custom-health-monitor.sh
