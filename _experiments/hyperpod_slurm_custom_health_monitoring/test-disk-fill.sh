#!/bin/bash

# Test utility to fill disk space for testing health monitor
# This script creates a large file to simulate disk space issues

set -euo pipefail

# Configuration
TEST_FILE="/tmp/disk-fill-test.bin"
CHUNK_SIZE_MB=100
TARGET_USAGE=92  # Target disk usage percentage

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

get_disk_usage() {
    df -h / | awk 'NR==2 {print $5}' | sed 's/%//'
}

get_available_space_mb() {
    df -BM / | awk 'NR==2 {print $4}' | sed 's/M//'
}

cleanup() {
    if [ -f "$TEST_FILE" ]; then
        log "Cleaning up test file..."
        rm -f "$TEST_FILE"
        log "Test file removed"
    fi
}

# Trap to ensure cleanup on exit
trap cleanup EXIT INT TERM

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Test utility to fill disk space for testing health monitor.

OPTIONS:
    -t, --target PERCENT    Target disk usage percentage (default: 92)
    -c, --cleanup           Remove test file and exit
    -s, --status            Show current disk usage and exit
    -h, --help              Show this help message

EXAMPLES:
    # Fill disk to 92% (triggers reboot threshold)
    sudo $0

    # Fill disk to 95%
    sudo $0 --target 95

    # Fill disk to 99% (triggers replacement threshold)
    sudo $0 --target 99

    # Check current disk usage
    $0 --status

    # Clean up test file
    sudo $0 --cleanup

NOTES:
    - This script requires root/sudo privileges to write large files
    - The test file is created at: $TEST_FILE
    - Use Ctrl+C to stop and cleanup
    - Health monitor thresholds:
      * 90-97%: Triggers reboot
      * ≥98%: Triggers replacement

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--target)
            TARGET_USAGE="$2"
            shift 2
            ;;
        -c|--cleanup)
            cleanup
            exit 0
            ;;
        -s|--status)
            current_usage=$(get_disk_usage)
            available_mb=$(get_available_space_mb)
            log "Current disk usage: ${current_usage}%"
            log "Available space: ${available_mb}MB"
            if [ -f "$TEST_FILE" ]; then
                test_file_size=$(du -m "$TEST_FILE" | awk '{print $1}')
                log "Test file exists: ${test_file_size}MB"
            fi
            exit 0
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate target usage
if [ "$TARGET_USAGE" -lt 1 ] || [ "$TARGET_USAGE" -gt 99 ]; then
    error "Target usage must be between 1 and 99"
    exit 1
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root (use sudo)"
    exit 1
fi

log "Starting disk fill test"
log "Target disk usage: ${TARGET_USAGE}%"
log "Test file location: $TEST_FILE"

# Get current disk usage
current_usage=$(get_disk_usage)
log "Current disk usage: ${current_usage}%"

if [ "$current_usage" -ge "$TARGET_USAGE" ]; then
    warn "Current disk usage (${current_usage}%) already meets or exceeds target (${TARGET_USAGE}%)"
    exit 0
fi

# Calculate how much space to fill
available_mb=$(get_available_space_mb)
log "Available space: ${available_mb}MB"

# Calculate space needed to reach target
# Formula: space_to_fill = available - (total * (100 - target) / 100)
total_mb=$(df -BM / | awk 'NR==2 {print $2}' | sed 's/M//')
space_to_fill=$(( available_mb - (total_mb * (100 - TARGET_USAGE) / 100) ))

if [ "$space_to_fill" -le 0 ]; then
    warn "Cannot calculate space to fill. Current usage may already exceed target."
    exit 0
fi

log "Space to fill: ${space_to_fill}MB"
log "This will take approximately $((space_to_fill / CHUNK_SIZE_MB)) iterations"

# Remove existing test file if present
if [ -f "$TEST_FILE" ]; then
    warn "Removing existing test file"
    rm -f "$TEST_FILE"
fi

# Fill disk in chunks
filled_mb=0
iteration=0

log "Starting to fill disk (press Ctrl+C to stop)..."

while [ "$filled_mb" -lt "$space_to_fill" ]; do
    iteration=$((iteration + 1))
    
    # Write chunk
    dd if=/dev/zero of="$TEST_FILE" bs=1M count=$CHUNK_SIZE_MB oflag=append conv=notrunc 2>/dev/null || {
        error "Failed to write chunk. Disk may be full."
        break
    }
    
    filled_mb=$((filled_mb + CHUNK_SIZE_MB))
    current_usage=$(get_disk_usage)
    
    log "Iteration $iteration: Filled ${filled_mb}MB / ${space_to_fill}MB (Current usage: ${current_usage}%)"
    
    # Check if we've reached target
    if [ "$current_usage" -ge "$TARGET_USAGE" ]; then
        log "Target disk usage reached!"
        break
    fi
    
    # Safety check - stop if we're getting too close to 100%
    if [ "$current_usage" -ge 99 ]; then
        warn "Disk usage at 99% - stopping for safety"
        break
    fi
    
    sleep 1
done

# Final status
final_usage=$(get_disk_usage)
test_file_size=$(du -m "$TEST_FILE" | awk '{print $1}')

echo ""
log "=== Disk Fill Test Complete ==="
log "Final disk usage: ${final_usage}%"
log "Test file size: ${test_file_size}MB"
log "Test file location: $TEST_FILE"
echo ""

if [ "$final_usage" -ge 98 ]; then
    warn "Disk usage ≥98% - Health monitor should trigger REPLACEMENT"
elif [ "$final_usage" -ge 90 ]; then
    warn "Disk usage ≥90% - Health monitor should trigger REBOOT"
else
    log "Disk usage below thresholds - Health monitor will not trigger"
fi

echo ""
log "To monitor health monitor logs, run:"
echo "  sudo journalctl -u custom-health-monitor -f"
echo ""
log "To clean up the test file, run:"
echo "  sudo $0 --cleanup"
echo ""
