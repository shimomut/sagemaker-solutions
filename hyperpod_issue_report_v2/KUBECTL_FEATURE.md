# Kubectl Integration Feature

## Overview

Added kubectl integration to the HyperPod Issue Report Collector v2 to capture Kubernetes node information for HyperPod EKS clusters.

## What's New

### 1. Automatic EKS Cluster Detection
- Extracts EKS cluster ARN from HyperPod cluster description
- Extracts EKS cluster name from the ARN
- Stores cluster information for kubectl configuration

### 2. Kubectl Configuration Verification
- Checks if kubectl is installed on the local machine
- Verifies kubectl is configured for the correct EKS cluster
- Displays clear instructions if kubectl is not configured
- Does NOT automatically configure kubectl (user maintains control)

### 3. Node Information Collection
- Executes `kubectl describe nodes` (all nodes in one command)
- Captures comprehensive node information including:
  - Node conditions (Ready, MemoryPressure, DiskPressure, etc.)
  - Capacity and allocatable resources (CPU, memory, pods, GPUs)
  - System information (OS, kernel, container runtime)
  - Pod information and resource usage
  - Node events and conditions
- Saves output as a single file with all nodes
- Creates a tarball and uploads to S3

### 4. Graceful Degradation
- If kubectl is not available, the tool continues with SSM-based collection
- If kubectl configuration fails, a warning is shown with manual configuration instructions
- Collection from nodes via SSM is not affected by kubectl issues

## Implementation Details

### New Methods

1. **`verify_kubectl_config()`**
   - Checks kubectl installation
   - Verifies current context matches EKS cluster
   - Displays helpful error messages with exact commands to run
   - Returns success/failure status
   - Main collection method
   - Runs `kubectl describe nodes` (all nodes in one command)
   - Saves combined output to single file
   - Creates tarball with output
   - Uploads to S3

### Modified Methods

1. **`__init__()`**
   - Added `eks_client` for EKS API calls
   - Added `eks_cluster_arn` and `eks_cluster_name` attributes

2. **`get_cluster_nodes()`**
   - Extracts EKS cluster ARN from orchestrator configuration
   - Extracts EKS cluster name from ARN
   - Logs EKS cluster information

3. **`collect_reports()`**
   - Calls `collect_kubectl_node_info()` before SSM collection
   - Only runs for EKS clusters

## Output Structure

### S3 Layout
```
s3://bucket/prefix/cluster-name/timestamp/
├── kubectl_nodes_timestamp.tar.gz    # NEW: kubectl output
├── collector_script.sh
├── summary.json
└── results/
    ├── worker1_i-xxx.tar.gz
    └── worker2_i-yyy.tar.gz
```

### Kubectl Tarball Contents
```
kubectl_output_timestamp/
└── all_nodes_describe.txt    # All nodes in one file
```

## Usage

No changes to command-line interface. The feature works automatically for EKS clusters:

```bash
# Step 1: Configure kubectl (one-time setup)
aws eks update-kubeconfig --name <eks-cluster-name> --region <region>

# Step 2: Run the tool (works the same as before)
python hyperpod_issue_report_v2.py \
  --cluster my-eks-cluster \
  --s3-path s3://my-bucket

# kubectl collection happens automatically if:
# 1. Cluster is EKS type
# 2. kubectl is installed
# 3. kubectl is configured for the correct EKS cluster
```

If kubectl is not configured, the tool will display:
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
kubectl context 'arn:aws:eks:...:other-cluster' does not match EKS cluster
Expected cluster: my-eks-cluster
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2

Skipping kubectl collection. SSM-based collection will continue.
```

## Prerequisites

### For kubectl Collection (Optional)

1. **kubectl installed**:
   ```bash
   # macOS
   brew install kubectl
   
   # Linux
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   chmod +x kubectl
   sudo mv kubectl /usr/local/bin/
   ```

2. **AWS credentials with EKS permissions**:
   ```json
   {
     "Effect": "Allow",
     "Action": ["eks:DescribeCluster"],
     "Resource": "*"
   }
   ```

## Benefits

1. **Comprehensive View**: Combines node-level diagnostics (via SSM) with cluster-level Kubernetes information
2. **Troubleshooting**: kubectl output helps diagnose pod scheduling issues, resource constraints, and node conditions
3. **User Control**: Users configure kubectl themselves, maintaining control over their environment
4. **Clear Feedback**: Displays exact commands needed when kubectl is not configured
5. **Non-blocking**: SSM collection continues even if kubectl is not configured
6. **Centralized**: All diagnostics stored in one S3 location

## Troubleshooting

### kubectl not found
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
kubectl not found in PATH
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To collect kubectl node information, install kubectl:
  macOS:  brew install kubectl
  Linux:  https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/

Skipping kubectl collection. SSM-based collection will continue.
```

**Solution**: Install kubectl and re-run the tool

### kubectl not configured
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
No kubectl context configured
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2

Skipping kubectl collection. SSM-based collection will continue.
```

**Solution**: Run the displayed command and re-run the tool

### Wrong cluster configured
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
kubectl context 'arn:aws:eks:...:other-cluster' does not match EKS cluster
Expected cluster: my-eks-cluster
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2

Skipping kubectl collection. SSM-based collection will continue.
```

**Solution**: Run the displayed command to switch to the correct cluster

### Collection continues
In all cases, SSM-based collection from nodes continues normally. You can always re-run the tool after configuring kubectl to collect the kubectl information.

## Testing

To test the feature:

1. **With EKS cluster**:
   ```bash
   python hyperpod_issue_report_v2.py \
     --cluster my-eks-cluster \
     --s3-path s3://test-bucket \
     --debug
   ```
   
   Expected output:
   - "Detected cluster type: EKS"
   - "EKS Cluster ARN: arn:aws:eks:..."
   - "Collecting kubectl node information..."
   - "✓ Successfully uploaded kubectl node information to S3"

2. **Without kubectl**:
   - Uninstall or remove kubectl from PATH
   - Run the tool
   - Should see: "Warning: kubectl is not installed or not in PATH"
   - SSM collection should continue normally

3. **With Slurm cluster**:
   ```bash
   python hyperpod_issue_report_v2.py \
     --cluster my-slurm-cluster \
     --s3-path s3://test-bucket
   ```
   
   Expected output:
   - "Detected cluster type: Slurm"
   - "Skipping kubectl collection - not an EKS cluster"

## Future Enhancements

Potential improvements:
- Add `kubectl get pods --all-namespaces` output
- Collect pod logs for failed pods
- Add `kubectl top nodes` for resource usage
- Support for custom kubectl commands via CLI flags
