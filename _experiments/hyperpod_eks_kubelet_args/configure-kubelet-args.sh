#!/bin/bash
# Simple script to configure kubelet arguments for HyperPod EKS
# Usage: ./configure-kubelet-args.sh [max-pods] [kube-reserved-cpu] [kube-reserved-memory]
# Example: ./configure-kubelet-args.sh 110 100m 1Gi

set -ex

MAX_PODS=${1:-110}
KUBE_RESERVED_CPU=${2:-100m}
KUBE_RESERVED_MEMORY=${3:-1Gi}

KUBELET_SERVICE_FILE="/etc/systemd/system/kubelet.service"
SYSTEMD_DIR="/etc/systemd/system/kubelet.service.d"
DROP_IN_FILE="${SYSTEMD_DIR}/10-kubelet-args-override.conf"

echo "[INFO] Starting kubelet configuration"
echo "[INFO] Parameters: MAX_PODS=$MAX_PODS, KUBE_RESERVED_CPU=$KUBE_RESERVED_CPU, KUBE_RESERVED_MEMORY=$KUBE_RESERVED_MEMORY"

# Build additional arguments
ADDITIONAL_ARGS="--max-pods=$MAX_PODS --kube-reserved=cpu=$KUBE_RESERVED_CPU,memory=$KUBE_RESERVED_MEMORY --system-reserved=cpu=100m,memory=500Mi --eviction-hard=memory.available<200Mi,nodefs.available<10%"
echo "[INFO] Additional arguments: $ADDITIONAL_ARGS"

# Create directory
echo "[INFO] Creating directory: $SYSTEMD_DIR"
mkdir -p "$SYSTEMD_DIR"

# Write drop-in configuration with new environment variable
echo "[INFO] Writing configuration to: $DROP_IN_FILE"
cat > "$DROP_IN_FILE" <<EOF
[Service]
# Additional kubelet arguments for HyperPod
Environment="HYPERPOD_KUBELET_ARGS=$ADDITIONAL_ARGS"
EOF

echo "[INFO] Drop-in configuration written:"
cat "$DROP_IN_FILE"

# Modify the main kubelet.service file to append HYPERPOD_KUBELET_ARGS
echo "[INFO] Modifying $KUBELET_SERVICE_FILE to append HYPERPOD_KUBELET_ARGS"
if [ -f "$KUBELET_SERVICE_FILE" ]; then
    echo "[INFO] Original kubelet.service:"
    cat "$KUBELET_SERVICE_FILE"
    
    # Replace ExecStart line to append $HYPERPOD_KUBELET_ARGS
    sed -i 's|^ExecStart=/usr/bin/kubelet \$NODEADM_KUBELET_ARGS$|ExecStart=/usr/bin/kubelet $NODEADM_KUBELET_ARGS $HYPERPOD_KUBELET_ARGS|' "$KUBELET_SERVICE_FILE"
    
    echo "[INFO] Modified kubelet.service:"
    cat "$KUBELET_SERVICE_FILE"
else
    echo "[ERROR] $KUBELET_SERVICE_FILE not found"
    exit 1
fi

# Reload systemd to pick up changes
echo "[INFO] Reloading systemd daemon"
systemctl daemon-reload

echo "[INFO] Verifying systemd can see the configuration"
systemctl show kubelet.service -p Environment --no-pager

echo "[SUCCESS] Kubelet configuration completed"
echo "[INFO] Kubelet will start with additional arguments when HyperPod starts it"
