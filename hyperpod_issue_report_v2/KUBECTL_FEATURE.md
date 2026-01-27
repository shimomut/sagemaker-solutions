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

### 3. Comprehensive Kubernetes Resource Collection
- Collects 15 different Kubernetes resource types in a single efficient operation
- **High Priority Resources** (essential for troubleshooting):
  - Nodes: Detailed descriptions with capacity, conditions, and running pods
  - Pods: All pods across namespaces with detailed descriptions
  - Events: Cluster events sorted by timestamp
  - PVCs: PersistentVolumeClaims and detailed descriptions (storage issues)
  - Services: Network endpoints and detailed descriptions
- **Medium Priority Resources** (very useful):
  - Deployments, StatefulSets, DaemonSets: Workload configurations
  - ConfigMaps, Secrets: Configuration metadata (no sensitive content)
  - ResourceQuotas: Resource limits and usage
  - NetworkPolicies: Network isolation rules
- Each resource type saved as a separate file
- Creates a tarball with all resources at root level (no wrapper directory)
- Uploads to S3 as `kubectl_resources.tar.gz`

### 4. Fail-Fast for EKS Clusters
- **IMPORTANT**: For EKS clusters, kubectl is REQUIRED
- Tool exits with error if kubectl is not configured for EKS clusters
- Displays exact commands needed to configure kubectl
- Users must configure kubectl before running the tool
- This ensures complete diagnostic data is collected for EKS clusters

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
├── kubectl_resources.tar.gz    # NEW: kubectl resources (15 types)
├── collector_script.sh
├── summary.json
└── results/
    ├── worker1_i-xxx.tar.gz
    └── worker2_i-yyy.tar.gz
```

### Kubectl Tarball Contents
Files are at root level (no wrapper directory):
```
nodes_describe.txt                      # Node descriptions
pods_all_namespaces.txt                 # All pods (wide output)
pods_describe_all_namespaces.txt        # Detailed pod descriptions
events_all_namespaces.txt               # Cluster events
pvcs_all_namespaces.txt                 # PersistentVolumeClaims
pvcs_describe_all_namespaces.txt        # Detailed PVC descriptions
services_all_namespaces.txt             # Services
services_describe_all_namespaces.txt    # Detailed service descriptions
deployments_all_namespaces.txt          # Deployments
statefulsets_all_namespaces.txt         # StatefulSets
daemonsets_all_namespaces.txt           # DaemonSets
configmaps_all_namespaces.txt           # ConfigMaps
secrets_all_namespaces.txt              # Secrets (metadata only)
resourcequotas_all_namespaces.txt       # Resource quotas
networkpolicies_all_namespaces.txt      # Network policies
```

## Usage

**IMPORTANT**: For EKS clusters, kubectl MUST be configured before running the tool.

```bash
# Step 1: Configure kubectl (REQUIRED for EKS clusters)
aws eks update-kubeconfig --name <eks-cluster-name> --region <region>

# Verify configuration
kubectl get nodes

# Step 2: Run the tool
python hyperpod_issue_report_v2.py \
  --cluster my-eks-cluster \
  --s3-path s3://my-bucket

# kubectl collection happens automatically for EKS clusters
# Tool will exit with error if kubectl is not configured
```

If kubectl is not configured, the tool will display an error and exit:
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: kubectl must be configured for EKS clusters
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Please configure kubectl and re-run the tool.
```

If kubectl is configured for the wrong cluster:
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: kubectl context does not match EKS cluster
Current context: arn:aws:eks:...:other-cluster
Expected cluster: my-eks-cluster
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2
```

## Prerequisites

### For EKS Clusters (REQUIRED)

1. **kubectl installed**:
   ```bash
   # macOS
   brew install kubectl
   
   # Linux
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   chmod +x kubectl
   sudo mv kubectl /usr/local/bin/
   ```

2. **kubectl configured for the EKS cluster**:
   ```bash
   aws eks update-kubeconfig --name <eks-cluster-name> --region <region>
   kubectl get nodes  # Verify configuration
   ```

3. **AWS credentials with EKS permissions**:
   ```json
   {
     "Effect": "Allow",
     "Action": ["eks:DescribeCluster"],
     "Resource": "*"
   }
   ```

## Benefits

1. **Comprehensive View**: Combines node-level diagnostics (via SSM) with cluster-level Kubernetes information
2. **15 Resource Types**: Collects essential and useful Kubernetes resources in one operation
3. **Troubleshooting**: kubectl output helps diagnose pod scheduling issues, resource constraints, node conditions, storage issues, and networking problems
4. **User Control**: Users configure kubectl themselves, maintaining control over their environment
5. **Clear Feedback**: Displays exact commands needed when kubectl is not configured
6. **Fail-Fast**: Ensures complete diagnostic data by requiring kubectl for EKS clusters
7. **Centralized**: All diagnostics stored in one S3 location
8. **Clean Structure**: Tarball files at root level for easy extraction and viewing

## Troubleshooting

### kubectl not found
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: kubectl is not installed or not in PATH
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

kubectl is required for EKS cluster diagnostics.

To install kubectl:
  macOS:  brew install kubectl
  Linux:  https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/
```

**Solution**: Install kubectl and re-run the tool. Tool exits with error for EKS clusters.

### kubectl not configured
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: No kubectl context configured
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2
```

**Solution**: Run the displayed command and re-run the tool. Tool exits with error for EKS clusters.

### Wrong cluster configured
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ERROR: kubectl context does not match EKS cluster
Current context: arn:aws:eks:...:other-cluster
Expected cluster: my-eks-cluster
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

To configure kubectl for this EKS cluster, run:
  aws eks update-kubeconfig --name my-eks-cluster --region us-west-2
```

**Solution**: Run the displayed command to switch to the correct cluster. Tool exits with error for EKS clusters.

### Tool exits for EKS clusters
For EKS clusters, the tool will exit with an error if kubectl is not properly configured. This ensures complete diagnostic data is collected. Configure kubectl and re-run the tool.

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

2. **Without kubectl (EKS cluster)**:
   - Uninstall or remove kubectl from PATH
   - Run the tool
   - Should see: "ERROR: kubectl is not installed or not in PATH"
   - Tool should exit with error code 1

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
- Add `kubectl top nodes` and `kubectl top pods` for real-time resource usage
- Collect pod logs for failed/pending pods automatically
- Add low-priority resources (ingresses, jobs, cronjobs, etc.)
- Support for custom kubectl commands via CLI flags
- Add namespace filtering option
