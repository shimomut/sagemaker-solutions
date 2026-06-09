#!/bin/bash
# Fill /var/log to a target percentage. Used for slurm-case-4 / disk-pressure.
set -euo pipefail

TEST_FILE="/var/log/hp-troubleshoot-disk-fill.bin"
TARGET=95
CHUNK_MB=200

usage() {
  cat <<EOF
Usage: sudo $0 [--target N] [--cleanup] [--status]
  --target N   Fill / until df reports N% used (default 95, max 98).
  --cleanup    Remove the test file.
  --status     Print current usage and exit.
EOF
}

du_pct() { df -h / | awk 'NR==2 {print $5}' | tr -d '%'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --target)  TARGET="$2"; shift 2 ;;
    --cleanup) rm -f "$TEST_FILE"; echo "removed $TEST_FILE"; exit 0 ;;
    --status)  echo "/ usage: $(du_pct)% test file: $([ -f "$TEST_FILE" ] && du -m "$TEST_FILE" | awk '{print $1"MB"}' || echo "absent")"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

if [ "$EUID" -ne 0 ]; then echo "must run as root"; exit 1; fi
if [ "$TARGET" -gt 98 ] || [ "$TARGET" -lt 50 ]; then
  echo "TARGET must be between 50 and 98 for safety"; exit 1
fi

echo "filling / until $TARGET% used (current: $(du_pct)%)"
while [ "$(du_pct)" -lt "$TARGET" ]; do
  if ! dd if=/dev/zero of="$TEST_FILE" bs=1M count="$CHUNK_MB" oflag=append conv=notrunc status=none 2>/dev/null; then
    echo "dd failed (likely full)"; break
  fi
  echo "  current: $(du_pct)%"
  sleep 0.2
done
echo "done. $(du_pct)% used. cleanup with: sudo $0 --cleanup"
