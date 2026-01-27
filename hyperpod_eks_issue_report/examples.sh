#!/bin/bash
# Example usage scripts for HyperPod EKS Issue Report Collector

# Set your cluster and S3 path
CLUSTER="my-hyperpod-cluster"
S3_PATH="s3://my-diagnostics-bucket"

echo "HyperPod EKS Issue Report Collector - Examples"
echo "=============================================="
echo ""

# Example 1: Basic collection (nvidia-smi + EKS logs collected by default)
echo "Example 1: Basic collection with defaults"
echo "------------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH"
echo ""

# Example 2: Additional GPU diagnostics
echo "Example 2: Additional GPU diagnostics"
echo "--------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'nvidia-smi -q' \\"
echo "  --command 'nvidia-smi topo -m' \\"
echo "  --command 'nvidia-smi dmon -c 1'"
echo ""

# Example 3: System health check
echo "Example 3: Additional system health checks"
echo "-------------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'uptime' \\"
echo "  --command 'free -h' \\"
echo "  --command 'top -bn1 | head -30' \\"
echo "  --command 'ps aux | head -20'"
echo ""

# Example 4: Kubernetes diagnostics
echo "Example 4: Kubernetes diagnostics"
echo "----------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'kubectl get nodes -o wide' \\"
echo "  --command 'kubectl get pods --all-namespaces' \\"
echo "  --command 'kubectl top nodes' \\"
echo "  --command 'kubectl describe nodes'"
echo ""

# Example 5: Network diagnostics
echo "Example 5: Network diagnostics"
echo "------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'ip addr show' \\"
echo "  --command 'ip route show' \\"
echo "  --command 'ss -tulpn' \\"
echo "  --command 'netstat -i' \\"
echo "  --command 'cat /etc/resolv.conf'"
echo ""

# Example 6: Target specific instance group
echo "Example 6: Target specific instance group"
echo "------------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --instance-group worker-group"
echo ""

# Example 7: Target specific nodes
echo "Example 7: Target specific nodes"
echo "---------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --nodes i-abc123 i-def456"
echo ""

# Example 8: Docker/Container diagnostics
echo "Example 8: Docker/Container diagnostics"
echo "---------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'docker ps -a' \\"
echo "  --command 'docker images' \\"
echo "  --command 'docker stats --no-stream' \\"
echo "  --command 'crictl ps -a'"
echo ""

# Example 9: Storage diagnostics
echo "Example 9: Storage diagnostics"
echo "------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'df -i' \\"
echo "  --command 'mount | grep -E \"(fsx|efs|nfs)\"' \\"
echo "  --command 'lsblk' \\"
echo "  --command 'du -sh /tmp /var/log'"
echo ""

# Example 10: EFA diagnostics (for ML workloads)
echo "Example 10: EFA diagnostics"
echo "---------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'fi_info -p efa' \\"
echo "  --command 'ibv_devinfo' \\"
echo "  --command 'ifconfig | grep -A 5 efa'"
echo ""

# Example 11: Custom S3 prefix and debug mode
echo "Example 11: Custom S3 prefix with debug"
echo "----------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path s3://my-bucket/diagnostics/gpu-issues/\$(date +%Y%m%d) \\"
echo "  --debug"
echo ""

# Example 12: Using Makefile shortcuts
echo "Example 12: Using Makefile shortcuts"
echo "------------------------------------"
echo "make run CLUSTER=$CLUSTER S3_PATH=$S3_PATH"
echo "make run-system CLUSTER=$CLUSTER S3_PATH=$S3_PATH"
echo "make run-k8s CLUSTER=$CLUSTER S3_PATH=$S3_PATH"
echo "make run-network CLUSTER=$CLUSTER S3_PATH=$S3_PATH"
echo ""

# Example 13: Comprehensive diagnostics with high concurrency
echo "Example 13: High concurrency collection"
echo "---------------------------------------"
echo "python hyperpod_eks_issue_report.py \\"
echo "  --cluster $CLUSTER \\"
echo "  --s3-path $S3_PATH \\"
echo "  --command 'hostname' \\"
echo "  --command 'kubectl get nodes' \\"
echo "  --command 'ip addr show' \\"
echo "  --max-workers 20"
echo ""

echo "To run any example, copy the command and replace the variables with your values."
echo "For more information, see README.md"
echo ""
echo "Note: The following are collected by default on every run:"
echo "  - nvidia-smi output"
echo "  - EKS log collector (comprehensive Kubernetes logs)"
echo "  - HyperPod resource config (/opt/ml/config/resource_config.json)"
echo "  - Cluster logs (/var/log/aws/clusters/*)"
echo "  - Systemd services status"
echo "  - Disk usage (df)"
