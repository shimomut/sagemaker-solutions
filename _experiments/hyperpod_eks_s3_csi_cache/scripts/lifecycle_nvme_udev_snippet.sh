#!/usr/bin/env bash
#
# Option B only.
#
# Add the contents of this snippet to your HyperPod EKS lifecycle script
# (on_create_main.sh) so that NVMe instance-store devices are exposed under
# /dev/disk/kubernetes for the Local Volume Static Provisioner to discover.
#
# This matches the layout expected by the upstream eks-nvme-ssd.yaml provisioner
# manifest (storageClassMap: nvme-ssd -> hostDir /dev/disk/kubernetes).
#
# IMPORTANT:
#   The Local Volume Static Provisioner consumes WHOLE block devices. Do NOT
#   point it at the same NVMe device that the default lifecycle script already
#   mounts for kubelet/containerd (DISK_FOR_CONTAINERD_KUBELET=/opt/dlami/nvme).
#   Option B therefore requires an instance type with MORE THAN ONE NVMe
#   instance-store disk (e.g. p5.48xlarge has 8). On single-NVMe nodes use
#   Option A (emptyDir) instead.
#
# Reference:
#   https://github.com/awslabs/mountpoint-s3-csi-driver/blob/main/docs/CACHING.md

set -euo pipefail

cat <<'EOF' > /etc/udev/rules.d/90-kubernetes-discovery.rules
# Discover EC2 NVMe Instance Storage disks so the Kubernetes Local Volume Static
# Provisioner can pick them up from /dev/disk/kubernetes
KERNEL=="nvme[0-9]*n[0-9]*", ENV{DEVTYPE}=="disk", ATTRS{model}=="Amazon EC2 NVMe Instance Storage", ATTRS{serial}=="?*", SYMLINK+="disk/kubernetes/nvme-$attr{model}_$attr{serial}", OPTIONS="string_escape=replace"
EOF

udevadm control --reload && udevadm trigger

echo "udev rules installed. Instance-store NVMe devices now appear under /dev/disk/kubernetes:"
ls -la /dev/disk/kubernetes/ 2>/dev/null || echo "  (none yet — check that this instance type has NVMe instance store)"
