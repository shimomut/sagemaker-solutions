# HyperPod Issue Report Collector v2 - Architecture

Technical documentation for developers and contributors.

## System Architecture

### Components

1. **Orchestrator** (User's Machine)
   - Queries SageMaker API for cluster information
   - Generates bash collection scripts
   - Manages parallel SSM sessions
   - Collects and aggregates results

2. **AWS Services**
   - **SageMaker API**: Cluster and node information
   - **S3**: Script distribution and result storage
   - **SSM**: Remote command execution on nodes
   - **EKS API**: Kubernetes cluster information (EKS only)

3. **HyperPod Nodes**
   - Download collection scripts from S3
   - Execute diagnostic commands
   - Upload results to S3

### Execution Flow

1. **Initialization**
   - Query SageMaker `DescribeCluster` to detect cluster type (EKS/Slurm)
   - Query SageMaker `ListClusterNodes` with pagination
   - Filter nodes by instance group or instance ID if specified

2. **kubectl Collection** (EKS only)
   - Verify kubectl configuration
   - Collect 15 Kubernetes resource types
   - Upload kubectl_resources.tar.gz to S3

3. **Script Generation**
   - Generate cluster-type-specific bash script
   - Script uses environment variables (INSTANCE_GROUP, INSTANCE_ID, CLUSTER_TYPE)
   - Upload single script to S3

4. **Parallel Execution**
   - ThreadPoolExecutor with configurable max_workers (default: 16)
   - Each worker:
     - Connects via SSM: `sagemaker-cluster:{cluster-id}_{instance-group}-{instance-id}`
     - Uses pexpect for interactive session management
     - Downloads script from S3
     - Executes script with environment variables
     - Script uploads results to S3

5. **Result Aggregation**
   - Collect execution results from all workers
   - Generate summary.json with success/failure status
   - Upload summary to S3
   - Optionally download all results locally

### Concurrency Model

```
Main Thread
    │
    ├─→ ThreadPoolExecutor (max_workers=16)
    │       │
    │       ├─→ Worker 1: Node 1 → SSM → Execute
    │       ├─→ Worker 2: Node 2 → SSM → Execute
    │       ├─→ Worker 3: Node 3 → SSM → Execute
    │       └─→ Worker N: Node N → SSM → Execute
    │
    └─→ Collect Results → Generate Summary
```

## Timeout Configuration

Timeouts are defined as constants at the top of the script for easy customization:

```python
SSM_SCRIPT_EXECUTION_TIMEOUT = 900  # 15 minutes - script execution on nodes
SSM_PROMPT_TIMEOUT = 60             # 60 seconds - prompt detection and setup
KUBECTL_TIMEOUT = 600               # 10 minutes - all kubectl operations
```

### Test Results (130-node cluster)

- **kubectl commands**: 1-26s (longest: kubectl describe pods)
- **SSM node collection**: 31-48s per node
- **Success rate**: 99.2% (129/130 nodes)
- **Total time**: ~15 minutes with default concurrency

### Timeout Design

- Each `pexpect.expect()` call has explicit timeout
- No default session timeout
- Provides 10-20x safety margin over observed times

## Error Handling

### SSM Throttling Protection

- **Exponential backoff**: Retry up to 3 times with 2^attempt seconds wait
- **Configurable concurrency**: `--max-workers` parameter (default: 16)
- **Automatic detection**: Catches `ThrottlingException` and `Rate exceeded` errors

### Success Detection

Multiple indicators checked (any one indicates success):
1. Exit code == 0
2. "Successfully uploaded report to s3://" in output
3. "upload: ../../tmp/" and ".tar.gz to s3://" in output

This prevents false negatives from incomplete output capture.

### Failure Handling

- Individual node failures don't stop collection
- Failed nodes reported in summary with error details
- Last 15 lines of output included for debugging
- Partial results still collected and uploaded

## Cluster Type Detection

### Auto-Detection Logic

```python
orchestrator = response.get('Orchestrator', {})

if 'Eks' in orchestrator:
    cluster_type = 'eks'
    # Extract EKS cluster ARN and name
elif 'Slurm' in orchestrator:
    cluster_type = 'slurm'
else:
    # Default to Slurm if Orchestrator field missing
    cluster_type = 'slurm'
```

### Type-Specific Collections

**EKS**:
- kubectl resource information (15 types)
- Containerd and kubelet service status
- AWS EKS log collector output

**Slurm**:
- sinfo and sinfo -R output
- Slurm services (slurmctld, slurmd)
- Slurm configuration and logs
- nvidia-bug-report

**Common**:
- nvidia-smi
- HyperPod resource config
- Cluster logs
- Systemd services
- Disk usage

## Node Identifier Resolution

### Supported Formats

1. **Instance IDs**: `i-0123456789abcdef0` (both EKS and Slurm)
2. **EKS node names**: `hyperpod-i-0123456789abcdef0` (EKS only)
3. **Slurm node names**: `ip-10-1-104-161` (Slurm only)

### Resolution Process

**EKS node names**:
- Extract instance ID by removing `hyperpod-` prefix
- Validate format starts with `i-`

**Slurm node names**:
- Call `describe_cluster_node` API for each node
- Extract private DNS hostname
- Build mapping: `{slurm_name: instance_id}`
- Resolve requested names to instance IDs

## S3 Structure

```
s3://bucket/prefix/cluster-name/YYYYMMDD_HHMMSS/
├── collector_script.sh              # Single script (uses env vars)
├── summary.json                     # Collection status
├── kubectl_resources.tar.gz         # kubectl output (EKS only)
└── instances/
    ├── {group}_{instance-id}.tar.gz
    └── ...
```

### Filename Format

Result tarballs: `{instance-group}_{instance-id}.tar.gz`
- Example: `worker1_i-0123456789abcdef0.tar.gz`

## Performance Characteristics

### Timing

- **Overhead**: ~10-30 seconds (API calls, script generation)
- **Node execution**: 31-48 seconds per node (130-node cluster)
- **kubectl collection**: 1-26 seconds total (15 resource types)
- **Total time**: ~15 minutes for 130 nodes with 16 workers

### Scalability

- **Tested**: 130 nodes, 99.2% success rate
- **Concurrency**: Default 16 workers balances speed and throttling
- **Bottleneck**: AWS SSM rate limits (mitigated with retry logic)

### Recommendations

- **100-200 nodes**: Use default `--max-workers 16`
- **200+ nodes**: Consider batching by instance group
- **Throttling**: Reduce to `--max-workers 8`
- **No throttling**: Increase to `--max-workers 32`

## Security Considerations

### Network Requirements

- Nodes must have SSM Agent running
- Nodes must have network access to S3
- Security groups must allow SSM traffic (port 443)

### IAM Requirements

**User/Role running tool**:
- `sagemaker:DescribeCluster`
- `sagemaker:ListClusterNodes`
- `sagemaker:DescribeClusterNode`
- `ssm:StartSession`
- `s3:PutObject`, `s3:GetObject`
- `eks:DescribeCluster` (EKS only)

**Node IAM roles**:
- `s3:GetObject` (download scripts)
- `s3:PutObject` (upload results)

### Data Collected

- System logs and configurations (no application data)
- Kubernetes resource metadata (no secret content)
- Service status and diagnostics
- No sensitive credentials or keys

## Comparison with v1

### hyperpod_issue_report (v1)

- **Connectivity**: SSH
- **Access**: Requires head node
- **Clusters**: Slurm only
- **Distribution**: Direct file system access
- **Node types**: Differentiates head/worker

### hyperpod_issue_report_v2 (v2)

- **Connectivity**: SSM
- **Access**: No head node required
- **Clusters**: Both EKS and Slurm
- **Distribution**: S3-based
- **Node types**: Treats all nodes uniformly

## kubectl Collection Details

### Resource Types Collected

**High Priority** (essential for troubleshooting):
- Nodes: Detailed descriptions with capacity, conditions, running pods
- Pods: All pods across namespaces with detailed descriptions
- Events: Cluster events sorted by timestamp
- PVCs: PersistentVolumeClaims and detailed descriptions
- Services: Network endpoints and detailed descriptions

**Medium Priority** (very useful):
- Deployments, StatefulSets, DaemonSets
- ConfigMaps, Secrets (metadata only)
- ResourceQuotas, NetworkPolicies

### Collection Strategy

- Single efficient collection (15 resource types)
- Runs from local machine (not from nodes)
- Uploaded as separate tarball: `kubectl_resources.tar.gz`
- Timing information displayed for each resource type

## Related Tools

- **hyperpod_run_on_multi_nodes**: Interactive command execution on multiple nodes
- **hyperpod_issue_report**: SSH-based collector for Slurm clusters (v1, legacy)
- **AWS EKS Log Collector**: https://github.com/awslabs/amazon-eks-ami/blob/main/log-collector-script/linux/eks-log-collector.sh
