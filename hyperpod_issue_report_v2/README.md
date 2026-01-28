# HyperPod Issue Report Collector v2

A utility to collect diagnostic logs and configurations from multiple HyperPod nodes. Supports both HyperPod EKS and HyperPod Slurm clusters with automatic cluster type detection. The tool downloads a collection script from S3, executes it on all specified nodes via SSM, and uploads the results back to S3.

## Features

- **Auto-detects cluster type** (EKS or Slurm) and collects appropriate diagnostics
- Collects diagnostic information from all nodes or specific instance groups
- **EKS clusters**: 
  - **Requires kubectl configured** - tool will exit if kubectl is not configured for the cluster
  - Automatically runs nvidia-smi and AWS EKS log collector on each node
  - Collects kubectl describe node information for all Kubernetes nodes
- **Slurm clusters**: Collects nvidia-smi, nvidia-bug-report, sinfo, Slurm services/config/logs, and system logs
- Downloads collection script from S3 to each node
- Executes multiple commands on each node
- Uploads individual node reports to S3 as compressed tarballs
- Generates a summary JSON with collection status
- **Interactive download**: Optionally download all results from S3 to local directory with zip archive creation
- Concurrent execution across multiple nodes
- Built on top of HyperPod SSM connectivity

## Quick Start

### Prerequisites

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure AWS credentials:
```bash
aws configure
```

3. **Ensure HyperPod instance execution roles have S3 permissions**:
   - The IAM roles attached to your HyperPod instance groups must have `s3:GetObject` and `s3:PutObject` permissions for your diagnostics bucket
   - See [IAM Policy Requirements](#iam-policy-requirements) section for details
   - You can add these permissions to existing IAM roles at any time

4. **For EKS clusters**: Ensure kubectl is installed and configured (REQUIRED):
```bash
# Configure kubectl for your EKS cluster
# Get the EKS cluster name from: aws sagemaker describe-cluster --cluster-name <hyperpod-cluster>
aws eks update-kubeconfig --name <eks-cluster-name> --region <region>

# Verify configuration
kubectl get nodes
```

**Note**: For EKS clusters, kubectl MUST be configured before running the tool. The tool will exit with an error if kubectl is not properly configured.

5. Create an S3 bucket for reports (if you don't have one):
```bash
aws s3 mb s3://my-diagnostics-bucket
```

### Basic Usage

The tool automatically detects cluster type and collects appropriate diagnostics:

```bash
# EKS cluster - REQUIRES kubectl configured first
# Step 1: Configure kubectl (if not already done)
aws eks update-kubeconfig --name <eks-cluster-name> --region <region>

# Step 2: Run the tool
python hyperpod_issue_report_v2.py \
  --cluster my-eks-cluster \
  --s3-path s3://my-diagnostics-bucket

# Slurm cluster - no kubectl needed
python hyperpod_issue_report_v2.py \
  --cluster my-slurm-cluster \
  --s3-path s3://my-diagnostics-bucket
```

### Using Makefile

```bash
# Basic collection (auto-detects cluster type)
make run CLUSTER=my-cluster S3_PATH=s3://my-bucket
```

### What Happens

1. Script queries SageMaker API to get cluster information and detect cluster type (EKS or Slurm)
2. Script queries SageMaker API to get all nodes in your cluster
3. **For EKS clusters**: Collects kubectl resource information for comprehensive cluster state
   - Verifies kubectl is installed and configured for the EKS cluster
   - If not configured, displays instructions and skips kubectl collection
   - Collects 15 resource types including nodes, pods, events, PVCs, services, deployments, etc.
   - Uploads kubectl output to S3 if successful
4. Generates a bash script that will:
   - **For EKS**: Run nvidia-smi, AWS EKS log collector, collect resource config, cluster logs, systemd services, disk usage
   - **For Slurm**: Run nvidia-smi, nvidia-bug-report, sinfo, collect Slurm services/config/logs, system logs
   - Run any additional commands you specified
5. Uploads the script to S3
6. Executes the script on all nodes via SSM concurrently
7. Each node uploads results to S3
8. Summary JSON is created with collection status
9. **Interactive download** (optional):
   - Tool asks if you want to download all results from S3 to current directory
   - If yes, downloads all files maintaining directory structure
   - Optionally creates a zip archive of downloaded results
   - Optionally deletes uncompressed directory after archiving

## Usage Examples

### Add Additional Commands

```bash
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --command "df -h" \
  --command "free -h" \
  --command "uptime"
```

### Target Specific Instance Groups

```bash
# Single instance group
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --instance-groups worker-group-1

# Multiple instance groups
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --instance-groups worker-group-1 worker-group-2 gpu-group
```

### Target Specific Nodes

For EKS clusters, use instance IDs or EKS node names:

```bash
# Using instance IDs
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --nodes i-abc123 i-def456

# Using EKS node names (hyperpod-i-* format)
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --nodes hyperpod-i-044bbf66a68558e87 hyperpod-i-055ccf77b79669f98
```

For Slurm clusters, use instance IDs or Slurm node names:

```bash
# Using instance IDs
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --nodes i-abc123 i-def456

# Using Slurm node names (ip-X-X-X-X format)
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --nodes ip-10-1-104-161 ip-10-1-104-162
```

### Custom S3 Prefix

```bash
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket/diagnostics/gpu-issues
```

### Debug Mode

```bash
python hyperpod_issue_report_v2.py \
  --cluster my-hyperpod-cluster \
  --s3-path s3://my-diagnostics-bucket \
  --debug
```

### System Health Checks

```bash
python hyperpod_issue_report_v2.py \
  --cluster my-cluster \
  --s3-path s3://my-bucket \
  --command "uptime" \
  --command "free -h" \
  --command "df -h"
```

## What Gets Collected

The tool automatically detects cluster type and collects appropriate diagnostics:

### Common to Both Cluster Types

- **nvidia-smi output**: GPU status, utilization, memory, temperature
- **HyperPod resource config**: `/opt/ml/config/resource_config.json`
- **Cluster logs**: `/var/log/aws/clusters/*`
- **Systemd services**: Status of all systemd services
- **Disk usage**: `df` output

### EKS-Specific Collections

- **Kubectl resource information**: Comprehensive Kubernetes cluster state
  - Collected from local machine (not from nodes)
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
  - Single efficient collection with 15 resource types
  - Uploaded as separate tarball: `kubectl_resources.tar.gz`
- **Containerd service status**: `systemctl status containerd` output
- **Kubelet service status**: `systemctl status kubelet` output
- **EKS log collector**: Comprehensive diagnostics including:
  - **CNI**: CNI plugin logs and configuration
  - **Containerd**: Container runtime logs, config, version, namespaces, images, containers, tasks, plugins
  - **Docker**: Docker logs (if present)
  - **GPU**: GPU-related logs and diagnostics
  - **IPAMD**: AWS VPC CNI IPAMD logs
  - **Kernel**: dmesg output (current and human-readable), uname info
  - **Kubelet**: Kubelet logs and configuration
  - **Modinfo**: Kernel module information (lustre, ip_vs, etc.)
  - **Networking**: Network configuration, iptables, routes, interfaces
  - **Nodeadm**: Node administration logs
  - **Sandbox-image**: Sandbox image information
  - **Storage**: Mounts, inodes, lsblk, LVM (lvs, pvs, vgs), fstab, XFS info, pod local storage
  - **Sysctls**: Kernel parameters
  - **System**: Services, systemd-analyze, top, ps, netstat, procstat, CPU/IO throttling, last reboot
  - **var_log**: System logs from /var/log

### Slurm-Specific Collections

- **Slurm information**:
  - `sinfo` - Slurm node and partition information
  - `sinfo -R` - Reasons for node down/drain states
- **Slurm services**:
  - `systemctl status slurmctld` - Slurm controller daemon status
  - `systemctl status slurmd` - Slurm compute node daemon status
- **Slurm configuration**: `/opt/slurm/etc/*`
- **NVIDIA bug report**: `nvidia-bug-report.sh` output (compressed)
- **System logs**:
  - `/var/log/syslog` - System log
  - `/var/log/kern.log` - Kernel log
  - `dmesg -T` - Kernel ring buffer with timestamps
- **Slurm logs**: `/var/log/slurm/*`

You can add additional commands using `--command` flags.

## Command Line Options

- `--cluster, -c`: HyperPod cluster name (EKS or Slurm) (required)
- `--s3-path, -s`: S3 path for storing reports (required). Accepts formats:
  - `s3://bucket-name` (uses default prefix: hyperpod-issue-reports)
  - `s3://bucket-name/custom-prefix`
- `--command, -cmd`: Additional command to execute on nodes (can be specified multiple times)
- `--instance-groups, -g`: Target specific instance groups (e.g., `--instance-groups worker1 worker2`)
- `--nodes, -n`: Target specific nodes. Accepts:
  - Instance IDs: `i-0123456789abcdef0` (works for both EKS and Slurm)
  - EKS node names: `hyperpod-i-0123456789abcdef0` (EKS clusters only)
  - Slurm node names: `ip-10-1-104-161` (Slurm clusters only)
  - Example: `--nodes i-abc123 i-def456` or `--nodes hyperpod-i-044bbf66a68558e87` or `--nodes ip-10-1-104-161`
- `--max-workers, -w`: Maximum concurrent SSM sessions (default: 16, reduce if hitting throttling)
- `--debug, -d`: Enable debug mode

**Note**: 
- Cluster type is auto-detected from the cluster description
- Default collections vary by cluster type (see "What Gets Collected" section)
- `--instance-groups` and `--nodes` are mutually exclusive (cannot be used together)
- For Slurm clusters, Slurm node names are resolved to instance IDs using the `describe_cluster_node` API
- For EKS clusters, EKS node names (hyperpod-i-*) are converted to instance IDs by removing the prefix

## How It Works

The tool automatically detects your cluster type (EKS or Slurm) and collects appropriate diagnostics:

1. **Queries SageMaker API** to get cluster information and all nodes
2. **For EKS clusters**: Collects kubectl resource information (requires kubectl configured)
3. **Generates a collection script** tailored to your cluster type
4. **Uploads the script to S3** for distribution
5. **Connects to each node via SSM** and executes the script in parallel
6. **Each node collects diagnostics** and uploads results to S3
7. **Generates a summary** with collection status
8. **Optionally downloads** all results to your local machine

For technical details, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Output Structure

Results are stored in S3 with the following structure:

```
s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/
├── collector_script.sh              # Single script (uses env vars)
├── summary.json                     # Summary of collection status
├── kubectl_resources.tar.gz         # kubectl resources (EKS only)
└── instances/
    ├── worker1_i-0123456789abcdef0.tar.gz
    ├── worker1_i-0123456789abcdef1.tar.gz
    └── worker2_i-0123456789abcdef2.tar.gz
```

Each tarball contains:

```
hyperpod_report_worker1_i-0123456789abcdef0_20260126_143025/
├── instance_group.txt               # Instance group name
├── instance_id.txt                  # EC2 instance ID
├── cluster_type.txt                 # Cluster type (eks or slurm)
├── hostname.txt                     # Node hostname
├── timestamp.txt                    # Collection timestamp (UTC)
├── resource_config.json             # HyperPod resource config (if exists)
├── cluster_logs/                    # Cluster logs from /var/log/aws/clusters/ (if exists)
├── systemd_services.txt             # All systemd services status
├── disk_usage.txt                   # Disk usage (df output)
├── nvidia_smi.txt                   # nvidia-smi output (always collected)
├── containerd_status.txt            # Containerd service status (EKS only)
├── kubelet_status.txt               # Kubelet service status (EKS only)
├── eks-log-collector-output.txt    # EKS log collector execution log (EKS only)
├── eks-logs/                        # EKS log collector output (EKS only)
│   ├── cni/                         # CNI plugin logs and config
│   ├── containerd/                  # Containerd logs, config, version, images, containers, tasks
│   ├── docker/                      # Docker logs (if present)
│   ├── gpu/                         # GPU diagnostics
│   ├── ipamd/                       # AWS VPC CNI IPAMD logs
│   ├── kernel/                      # dmesg, uname
│   ├── kubelet/                     # Kubelet logs and config
│   ├── modinfo/                     # Kernel module info (lustre, ip_vs, etc.)
│   ├── networking/                  # Network config, iptables, routes
│   ├── nodeadm/                     # Node administration logs
│   ├── sandbox-image/               # Sandbox image info
│   ├── storage/                     # Mounts, inodes, lsblk, LVM, fstab, XFS, pod storage
│   ├── sysctls/                     # Kernel parameters
│   ├── system/                      # Services, systemd-analyze, top, ps, netstat, throttling
│   └── var_log/                     # System logs from /var/log
├── sinfo.txt                        # Slurm node info (Slurm clusters only)
├── sinfo_R.txt                      # Slurm node reasons (Slurm clusters only)
├── slurmctld_status.txt             # Slurm controller status (Slurm clusters only)
├── slurmd_status.txt                # Slurm daemon status (Slurm clusters only)
├── opt_slurm_etc/                   # Slurm configuration (Slurm clusters only)
├── nvidia-bug-report.log.gz         # NVIDIA bug report (Slurm clusters only)
├── syslog                           # System log (Slurm clusters only)
├── kern.log                         # Kernel log (Slurm clusters only)
├── dmesg_T.txt                      # Kernel ring buffer (Slurm clusters only)
├── var_log_slurm/                   # Slurm logs (Slurm clusters only)
├── command_01_df_-i.txt             # Additional user commands (if specified)
└── command_02_free_-h.txt
```

**Filename Format**: Result tarballs use the format `{instance-group}_{instance-id}.tar.gz` where:
- `instance-group`: The HyperPod instance group name (e.g., `worker1`, `worker2`)
- `instance-id`: The EC2 instance ID (e.g., `i-0123456789abcdef0`)

### View Results

#### Interactive Download (Recommended)

After collection completes, the tool will ask if you want to download results:

```
Would you like to download all results from S3 to the current directory? (y/n): y

Downloading results to: ./my-cluster_20260127_143022/
Source: s3://my-bucket/hyperpod-issue-reports/my-cluster/20260127_143022/
Found 15 files to download...
  Downloaded 5/15 files...
  Downloaded 10/15 files...
  Downloaded 15/15 files...

✓ Download completed!
  Downloaded: 15 files
  Location: ./my-cluster_20260127_143022/

Would you like to create a zip archive of the downloaded results? (y/n): y

Creating zip archive: my-cluster_20260127_143022.zip
  Archived 5 files...
  Archived 10 files...
  Archived 15 files...

✓ Zip archive created!
  File: my-cluster_20260127_143022.zip
  Size: 45.23 MB
  Files: 15

Would you like to delete the uncompressed directory 'my-cluster_20260127_143022'? (y/n): y
✓ Deleted directory: my-cluster_20260127_143022
```

The downloaded directory structure:
```
my-cluster_20260127_143022/
├── collector_script.sh
├── summary.json
├── kubectl_resources.tar.gz
└── instances/
    ├── worker1_i-0123456789abcdef0.tar.gz
    ├── worker1_i-0123456789abcdef1.tar.gz
    └── worker2_i-0123456789abcdef2.tar.gz
```

## Summary JSON Format

```json
{
  "cluster_name": "my-hyperpod-cluster",
  "cluster_id": "abc123",
  "report_id": "20260126_143022",
  "timestamp": "2026-01-26T14:30:22.123456",
  "total_nodes": 8,
  "successful": 7,
  "failed": 1,
  "results": [
    {
      "InstanceId": "i-0123456789abcdef0",
      "NodeGroup": "worker-group",
      "Success": true,
      "Output": "..."
    }
  ]
}
```

## IAM Policy Requirements

### For the User/Role Running the Tool

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sagemaker:DescribeCluster",
        "sagemaker:ListClusterNodes",
        "ssm:StartSession",
        "s3:PutObject",
        "s3:GetObject",
        "eks:DescribeCluster"
      ],
      "Resource": "*"
    }
  ]
}
```

**Note**: For EKS clusters, kubectl MUST be configured before running the tool. The tool will exit with an error and display the exact command needed if kubectl is not properly configured.

### For HyperPod Instance Group IAM Roles

These permissions must be attached to the IAM roles associated with your HyperPod instance groups (configured during cluster creation).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::my-diagnostics-bucket/*"
    }
  ]
}
```

**Important Notes**:
- Replace `my-diagnostics-bucket` with your actual S3 bucket name
- S3 permissions are required to download collection scripts and upload diagnostic results
- The IAM role must be attached to instance groups when creating the HyperPod cluster
- Without these permissions, nodes cannot download scripts or upload results
  ]
}
```

## Troubleshooting

### No Instance Reports in S3

If you see `collector_script.sh` and `summary.json` but no files in the `instances/` folder:

1. **Check the summary.json** to see command execution status:
```bash
aws s3 cp s3://your-bucket/hyperpod-issue-reports/cluster/timestamp/summary.json -
```

Look for:
- `"Success": false` indicates the command failed
- Error messages in the `"Error"` field
- Last 15 lines of output showing what went wrong

2. **Common causes**:
   - Node IAM role missing S3 write permissions
   - Script execution errors (check error output in summary)
   - Network connectivity issues to S3
   - Insufficient disk space on nodes
   - EKS log collector failed to produce tarball

3. **Verify node IAM role** has required permissions:
```bash
# Check if role has S3 permissions
aws iam get-role --role-name YourHyperPodNodeRole
aws iam list-attached-role-policies --role-name YourHyperPodNodeRole
```

4. **Test S3 access from nodes**:
```bash
# Connect to a node via SSM
aws ssm start-session --target sagemaker-cluster:{cluster-id}_{instance-group}-{instance-id}

# Test S3 access
aws s3 ls s3://your-bucket/
```

### SSM Connectivity Issues

If nodes fail to respond:
1. Verify SSM Agent is running: `sudo systemctl status amazon-ssm-agent`
2. Check IAM role has `AmazonSSMManagedInstanceCore` policy
3. Verify security groups allow SSM traffic
4. Check AWS credentials have SSM permissions
5. Ensure correct SSM target format: `sagemaker-cluster:{cluster-id}_{instance-group}-{instance-id}`

### Custom SSM Session Configuration

**Symptom**: Tool fails with "Failed to detect shell prompt" error showing custom bash commands in the output.

**Cause**: Your cluster has custom SSM session configuration (e.g., custom `.bashrc`, SSM session preferences, or lifecycle scripts that modify the shell prompt).

**Example error output**:
```
Failed to detect shell prompt after 90 seconds.
Session output received:
'/bin/bash -c 'export HOME=/fsx/$(whoami) && cd ${HOME} && exec /bin/bash'
h'-4.2# '/bin/bash -c 'export HOME=/fsx/$(whoami) && cd ${HOME} && exec /bin/bas
>
```

**Why this happens**:
- The tool expects standard shell prompts (ending with `$` or `#` followed by space)
- Custom SSM configurations may:
  - Execute commands on session start that interfere with prompt detection
  - Use non-standard prompt formats
  - Redirect or modify shell initialization

**Workaround**:
This tool is not compatible with clusters that have custom SSM session configurations. You may need to:
1. Temporarily disable custom SSM session commands
2. Use alternative collection methods (manual SSM sessions with script execution)
3. Modify the tool's prompt detection patterns to match your custom prompts

**To check your SSM configuration**:
```bash
# Test SSM session manually
aws ssm start-session --target sagemaker-cluster:{cluster-id}_{instance-group}-{instance-id}

# Observe the initial output and prompt format
```

### S3 Upload Failures

If uploads fail:
1. Verify S3 bucket exists and is accessible
2. Check IAM role on nodes has S3 write permissions
3. Verify bucket policy allows PutObject from node IAM role
4. Check network connectivity to S3 endpoints

### Script Execution Failures

If commands fail on nodes:
1. Test commands manually via SSM session
2. Check command syntax and availability
3. Verify required tools are installed on nodes
4. Use `--debug` flag for detailed error messages
5. Check last 15 lines of output in summary for specific errors

### EKS Log Collector Issues

If EKS log collector fails:
1. Check if the script downloaded successfully
2. Verify the script has execute permissions
3. Look for error messages in `eks-log-collector-output.txt`
4. Ensure sufficient disk space in `/var/log/` and `/tmp/`
5. Check if the tarball was created in `/var/log/eks_*.tar.gz`

### Kubectl Collection Issues (EKS only)

**IMPORTANT**: For EKS clusters, kubectl MUST be configured. The tool will exit with an error if kubectl is not properly configured.

If you see an error message, follow the instructions displayed:

1. **kubectl not installed**: Install kubectl and re-run the tool

2. **kubectl not configured**:
   ```bash
   # The tool will display the exact command you need to run
   # Example:
   aws eks update-kubeconfig --name sagemaker-k8-3-e32614e5-eks --region us-west-2
   
   # Verify
   kubectl get nodes
   
   # Re-run the collection tool
   python hyperpod_issue_report_v2.py --cluster <cluster> --s3-path <s3-path>
   ```

3. **Wrong context** (kubectl configured for different cluster):
   ```bash
   # Check current context
   kubectl config current-context
   
   # Configure for the correct cluster (command shown in error message)
   aws eks update-kubeconfig --name <correct-cluster-name> --region <region>
   
   # Verify
   kubectl get nodes
   ```

4. **Missing EKS permissions**: Ensure your AWS credentials have `eks:DescribeCluster` permission

## Large Cluster Handling (100+ Nodes)

The tool is optimized for large clusters (tested up to 130 nodes with 99.2% success rate):

- **Automatic retry with exponential backoff**: Handles AWS SSM throttling automatically
- **Balanced default concurrency**: Default `--max-workers 16` balances speed and reliability
- **Configurable concurrency**: Adjust `--max-workers` based on your cluster size

```bash
# For very large clusters (200+ nodes), reduce concurrency if hitting throttling
python hyperpod_issue_report_v2.py \
  --cluster my-large-cluster \
  --s3-path s3://my-bucket \
  --max-workers 8

# For smaller clusters or if you have higher SSM limits
python hyperpod_issue_report_v2.py \
  --cluster my-cluster \
  --s3-path s3://my-bucket \
  --max-workers 32
```

### Recommendations

1. **Default works well**: The default `--max-workers 16` balances speed and reliability
2. **Monitor for throttling**: Watch for `ThrottlingException` or `Rate exceeded` errors
3. **Adjust if needed**: 
   - If throttling occurs: reduce to `--max-workers 8`
   - If no throttling: increase to `--max-workers 32`
4. **Consider batching**: For 200+ nodes, run collection in batches by instance group

For technical details about timeouts and performance characteristics, see [ARCHITECTURE.md](ARCHITECTURE.md).

### Test Results

**130-node cluster:**
- **Success rate**: 129/130 nodes (99.2%)
- **Throttling**: Automatic retry handled all throttling errors
- **kubectl collection**: Completed successfully with extended timeouts
- **Total time**: ~15 minutes with default concurrency

**Projected for 1000-node cluster:**
- **kubectl describe**: ~20-30 minutes (within 30-minute timeout)
- **Node collection**: ~60-90 minutes with default concurrency (16 workers)
- **Recommendation**: Use `--max-workers 32` for faster collection if no throttling occurs

## Limitations

- Requires SSM connectivity to all nodes
- Commands must complete within 15 minutes per node
- Large output files may take time to upload to S3
- Concurrent execution limited by `--max-workers` setting and AWS SSM rate limits
- Nodes must have AWS CLI installed
- For clusters with 100+ nodes, expect 10-20% failure rate due to transient issues

## Technical Details

### Comparison with hyperpod_issue_report

**hyperpod_issue_report (v1, Slurm-based, SSH)**:
- Uses SSH for connectivity
- Requires head node access
- Slurm-specific commands only
- Direct file system access
- Differentiates between head and worker nodes

**hyperpod_issue_report_v2 (Universal, SSM)**:
- Supports both EKS and Slurm clusters
- Uses SSM for connectivity
- No head node required
- Auto-detects cluster type
- S3-based distribution and collection
- Treats all nodes uniformly

### Performance Characteristics

- Time = max(node_execution_time) + overhead
- Overhead: ~10-30 seconds (API calls, script generation)
- Node execution: depends on commands
- Typical: 1-5 minutes for basic diagnostics

### Security Considerations

**Network Requirements**:
- Nodes must have SSM Agent running
- Nodes must have network access to S3
- Security groups must allow SSM traffic

**Error Handling**:
- Individual node failures don't stop collection
- Failed nodes reported in summary with error details
- Partial results still collected
- Exit codes checked for each command

## Related Tools

- `hyperpod_run_on_multi_nodes`: Interactive command execution on multiple nodes (both EKS and Slurm)
- `hyperpod_issue_report`: SSH-based issue report collector for HyperPod Slurm clusters (v1, legacy)
- AWS EKS Log Collector: https://github.com/awslabs/amazon-eks-ami/blob/main/log-collector-script/linux/eks-log-collector.sh
