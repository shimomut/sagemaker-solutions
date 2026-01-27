# Changes Summary

## kubectl Integration for HyperPod EKS Clusters

### Overview
Added kubectl integration to collect Kubernetes node information for HyperPod EKS clusters. kubectl configuration is **required** for EKS clusters - the tool will exit with a clear error message if kubectl is not properly configured.

### Key Changes

#### 1. kubectl Requirement for EKS Clusters
- **BREAKING**: For EKS clusters, kubectl MUST be configured before running the tool
- Tool exits with error code 1 if kubectl is not configured
- Displays exact command needed to configure kubectl
- Slurm clusters are unaffected (no kubectl needed)

#### 2. Fixed kubectl Version Detection
- Removed deprecated `--short` flag from `kubectl version --client`
- Now compatible with kubectl v1.28+ (where `--short` was removed)
- Works with all kubectl versions

#### 3. Clear Error Messages
When kubectl is not configured, users see:
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: kubectl context does not match EKS cluster
Current context: arn:aws:eks:...:other-cluster
Expected cluster: my-eks-cluster
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: kubectl must be configured for EKS clusters
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Please configure kubectl and re-run the tool.
```

### Implementation Details

#### New Functionality
1. **EKS Cluster Detection**
   - Extracts EKS cluster ARN from HyperPod cluster orchestrator config
   - Derives EKS cluster name from ARN
   - Extracts region for kubectl configuration command

2. **kubectl Verification**
   - Checks kubectl installation
   - Verifies current context matches EKS cluster
   - Returns clear error messages with exact commands

3. **Node Information Collection**
   - Runs `kubectl get nodes -o json` to list all nodes
   - Executes `kubectl describe node` for each node
   - Creates tarball with all outputs
   - Uploads to S3: `kubectl_nodes_{timestamp}.tar.gz`

#### Modified Methods
- `__init__()`: Added `eks_client`, `eks_cluster_arn`, `eks_cluster_name`
- `get_cluster_nodes()`: Extracts and logs EKS cluster information
- `collect_reports()`: Calls kubectl collection before SSM collection
- `verify_kubectl_config()`: Enhanced error messages, removed `--short` flag
- `collect_kubectl_node_info()`: Exits on kubectl configuration failure

### Usage

#### For EKS Clusters (kubectl required)
```bash
# Step 1: Configure kubectl (one-time setup)
aws eks update-kubeconfig --name <eks-cluster-name> --region <region>

# Step 2: Verify configuration
kubectl get nodes

# Step 3: Run the tool
python hyperpod_issue_report_v2.py \
  --cluster my-eks-cluster \
  --s3-path s3://my-bucket
```

#### For Slurm Clusters (no change)
```bash
# Works exactly as before - no kubectl needed
python hyperpod_issue_report_v2.py \
  --cluster my-slurm-cluster \
  --s3-path s3://my-bucket
```

### Output Structure

```
s3://bucket/prefix/cluster/timestamp/
├── kubectl_nodes_timestamp.tar.gz    # NEW: kubectl output (EKS only)
│   └── kubectl_output_timestamp/
│       ├── ip-10-0-1-100.ec2.internal_describe.txt
│       ├── ip-10-0-1-101.ec2.internal_describe.txt
│       └── ip-10-0-1-102.ec2.internal_describe.txt
├── collector_script.sh
├── summary.json
└── results/
    ├── worker1_i-xxx.tar.gz
    └── worker2_i-yyy.tar.gz
```

### Migration Guide

#### If you have EKS clusters
Before running the updated tool, configure kubectl:
```bash
# Get EKS cluster name from HyperPod cluster
aws sagemaker describe-cluster --cluster-name <hyperpod-cluster>

# Configure kubectl (look for Orchestrator.Eks.ClusterArn in output)
aws eks update-kubeconfig --name <eks-cluster-name> --region <region>

# Verify
kubectl get nodes
```

#### If you have Slurm clusters
No changes needed - tool works exactly as before.

### Benefits

1. **Comprehensive Diagnostics**: Combines node-level (SSM) and cluster-level (kubectl) information
2. **Better Troubleshooting**: kubectl output helps diagnose pod scheduling, resource constraints, node conditions
3. **User Control**: Users maintain control over kubectl configuration
4. **Clear Feedback**: Exact commands displayed when configuration needed
5. **Fail-Fast**: Exits immediately if kubectl not configured (no wasted time)

### Troubleshooting

#### Error: kubectl not installed
```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
```

#### Error: kubectl context mismatch
```bash
# Run the command shown in the error message
aws eks update-kubeconfig --name <cluster-name> --region <region>

# Verify
kubectl get nodes
```

#### Error: No kubectl context configured
```bash
# Configure kubectl (command shown in error message)
aws eks update-kubeconfig --name <cluster-name> --region <region>
```

### Files Modified

1. **hyperpod_issue_report_v2.py**
   - Added kubectl integration
   - Fixed kubectl version detection
   - Made kubectl required for EKS clusters

2. **README.md**
   - Updated prerequisites (kubectl required for EKS)
   - Updated features section
   - Updated troubleshooting section
   - Updated usage examples

3. **KUBECTL_FEATURE.md** (new)
   - Comprehensive feature documentation

4. **CHANGES.md** (this file)
   - Summary of changes

### Testing

Tested with:
- kubectl v1.35.0 (latest)
- kubectl v1.28+ (without `--short` flag support)
- EKS clusters with HyperPod
- Slurm clusters (no kubectl needed)

### Compatibility

- **Python**: 3.7+
- **kubectl**: All versions (1.20+)
- **AWS CLI**: 2.x
- **boto3**: 1.26.0+
