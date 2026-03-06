.PHONY: help install uninstall status logs logs-all logs-follow restart stop start enable disable test-script test-disk-fill test-disk-status test-disk-cleanup

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
	@echo "  make test-script       - Test the health monitor script manually"
	@echo "  make test-disk-fill    - Fill disk to 99% to test replacement trigger"
	@echo "  make test-disk-status  - Check current disk usage"
	@echo "  make test-disk-cleanup - Remove test file and free disk space"

install:
	@echo "Installing HyperPod Slurm Custom Health Monitor..."
	@chmod +x install_custom_health_monitor.sh
	@sudo ./install_custom_health_monitor.sh

uninstall:
	@echo "Uninstalling HyperPod Slurm Custom Health Monitor..."
	@chmod +x uninstall_custom_health_monitor.sh
	@sudo ./uninstall_custom_health_monitor.sh

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

test-disk-fill:
	@echo "Filling disk to 99% to test replacement trigger..."
	@chmod +x test-disk-fill.sh
	@sudo ./test-disk-fill.sh --target 99

test-disk-status:
	@echo "Checking current disk usage..."
	@chmod +x test-disk-fill.sh
	@./test-disk-fill.sh --status

test-disk-cleanup:
	@echo "Cleaning up test file..."
	@chmod +x test-disk-fill.sh
	@sudo ./test-disk-fill.sh --cleanup
