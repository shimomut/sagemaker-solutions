#!/bin/bash
# Simple script to configure kubelet arguments for HyperPod EKS
# Usage: ./configure-kubelet.sh [max-pods] [kube-reserved-cpu] [kube-reserved-memory]
# Example: ./configure-kubelet.sh 110 100m 1Gi

set -e

MAX_PODS=${1:-110}
KUBE_RESERVED_CPU=${2:-100m}
KUBE_RESERVED_MEMORY=${3:-1Gi}

SYSTEMD_DIR="/etc/systemd/system/kubelet.service.d"
DROP_IN_FILE="${SYSTEMD_DIR}/10-kubelet-args-override.conf"

# Get current ExecStart
CURRENT_EXEC=$(systemctl cat kubelet.service | grep "^ExecStart=" | head -1 | sed 's/^ExecStart=//')

# Build new ExecStart with additional arguments
NEW_EXEC="$CURRENT_EXEC --max-pods=$MAX_PODS --kube-reserved=cpu=$KUBE_RESERVED_CPU,memory=$KUBE_RESERVED_MEMORY --system-reserved=cpu=100m,memory=500Mi --eviction-hard=memory.available<200Mi,nodefs.available<10%"

# Create directory
mkdir -p "$SYSTEMD_DIR"

# Write configuration
cat > "$DROP_IN_FILE" <<EOF
[Service]
# Override ExecStart to add additional kubelet arguments
ExecStart=
ExecStart=$NEW_EXEC
EOF

# Reload and restart
systemctl daemon-reload
systemctl restart kubelet
