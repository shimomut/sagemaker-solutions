# HyperPod EKS Issue Report Collector

A utility to collect diagnostic logs and configurations from multiple HyperPod EKS nodes. The tool downloads a collection script from S3, executes it on all specified nodes via SSM, and uploads the results back to S3.

## Features

- Collects diagnostic information from all nodes or specific instance groups
- Automatically runs nvidia-smi and AWS EKS log collector by default
- Downloads collection script from S3 to each node
- Executes multiple commands on each node
- Uploads individual node reports to S3 as compressed tarballs
- Generates a summary JSON with collection status
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

3. Create an S3 bucket for reports (if you don't have one):
```bash
aws s3 mb s3://my-diagnostics-bucket
```

### Basic Usage

The tool automatically collects nvidia-smi and EKS logs:

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket
```

### Using Makefile

```bash
# Basic collection (nvidia-smi + EKS logs)
make run CLUSTER=my-cluster S3_BUCKET=my-bucket
```

### What Happens

1. Script queries SageMaker API to get all nodes in your cluster
2. Generates a bash script that will:
   - Run nvidia-smi
   - Run AWS EKS log collector
   - Run any additional commands you specified
3. Uploads the script to S3
4. Executes the script on all nodes via SSM concurrently
5. Each node uploads results to S3
6. Summary JSON is created with collection status

## Usage Examples

### Add Additional Commands

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --command "df -h" \
  --command "free -h" \
  --command "uptime"
```

### Target Specific Instance Group

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --instance-group worker-group
```

### Custom S3 Prefix

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --s3-prefix diagnostics/gpu-issues
```

### Debug Mode

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --debug
```

### System Health Checks

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket my-bucket \
  --command "uptime" \
  --command "free -h" \
  --command "df -h"
```

## What Gets Collected

By default, the tool collects:

1. **nvidia-smi output**: GPU status, utilization, memory, temperature
2. **EKS log collector**: Comprehensive diagnostics including:
   - Kubelet logs and configuration
   - Container runtime logs
   - CNI plugin logs and configuration
   - Network configuration (iptables, routes, interfaces)
   - System logs (syslog, dmesg, journald)
   - Kernel parameters
   - EKS-specific diagnostics

You can add additional commands using `--command` flags.

## Command Line Options

- `--cluster, -c`: HyperPod cluster name (required)
- `--s3-bucket, -b`: S3 bucket for storing reports (required)
- `--s3-prefix, -p`: S3 prefix for reports (default: hyperpod-issue-reports)
- `--command, -cmd`: Additional command to execute on nodes (can be specified multiple times)
- `--instance-group, -g`: Target specific instance group only
- `--max-workers, -w`: Maximum concurrent workers (default: 10)
- `--debug, -d`: Enable debug mode

**Note**: nvidia-smi and EKS log collector are always run by default.

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Machine                          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  hyperpod_eks_issue_report.py                             │ │
│  │  - Queries SageMaker API for cluster nodes                │ │
│  │  - Generates collection script                            │ │
│  │  - Orchestrates parallel execution                        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │      AWS Services        │
              │                          │
              │  ┌────────────────────┐  │
              │  │  SageMaker API     │  │
              │  │  - List nodes      │  │
              │  │  - Get cluster info│  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  S3 Bucket         │  │
              │  │  - Store script    │  │
              │  │  - Store results   │  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  SSM Service       │  │
              │  │  - Execute commands│  │
              │  └────────────────────┘  │
              └──────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   HyperPod EKS Cluster   │
              │                          │
              │  ┌────────────────────┐  │
              │  │  Node 1            │  │
              │  │  - Download script │  │
              │  │  - Run commands    │  │
              │  │  - Upload results  │  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  Node 2            │  │
              │  │  - Download script │  │
              │  │  - Run commands    │  │
              │  │  - Upload results  │  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  Node N            │  │
              │  │  - Download script │  │
              │  │  - Run commands    │  │
              │  │  - Upload results  │  │
              │  └────────────────────┘  │
              └──────────────────────────┘
```

### Execution Flow

1. **Initialization**: Query SageMaker API for cluster nodes, filter by instance group if specified
2. **Script Generation**: Create bash collection script with user commands
3. **Script Distribution**: Upload collection script to S3
4. **Parallel Execution**: For each node (in parallel):
   - Connect via SSM using HyperPod target format: `sagemaker-cluster:{cluster-id}_{instance-group}-{instance-id}`
   - Download script from S3
   - Execute script with `INSTANCE_GROUP` and `INSTANCE_ID` environment variables
   - Script runs all commands
   - Script creates tarball
   - Script uploads tarball to S3
5. **Summary**: Collect execution results, generate summary JSON, upload to S3

### Concurrency Model

```
Main Thread
    │
    ├─→ ThreadPoolExecutor (max_workers=10)
    │       │
    │       ├─→ Worker 1: Node 1 → SSM → Execute
    │       ├─→ Worker 2: Node 2 → SSM → Execute
    │       ├─→ Worker 3: Node 3 → SSM → Execute
    │       └─→ Worker N: Node N → SSM → Execute
    │
    └─→ Collect Results → Generate Summary
```

## Output Structure

Results are stored in S3 with the following structure:

```
s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/
├── collector_script.sh              # Single script (uses env vars)
├── summary.json                     # Summary of collection status
└── results/
    ├── worker1_i-0123456789abcdef0.tar.gz
    ├── worker1_i-0123456789abcdef1.tar.gz
    └── worker2_i-0123456789abcdef2.tar.gz
```

Each tarball contains:

```
hyperpod_report_worker1_i-0123456789abcdef0_20260126_143025/
├── instance_group.txt               # Instance group name
├── instance_id.txt                  # EC2 instance ID
├── hostname.txt                     # Node hostname
├── timestamp.txt                    # Collection timestamp (UTC)
├── eks-logs/                        # EKS log collector output
│   ├── kubelet/
│   ├── docker/
│   ├── var_log/
│   └── ...
├── eks-log-collector-output.txt    # EKS log collector execution log
├── command_01_nvidia-smi.txt
├── command_02_df_-h.txt
└── command_03_free_-h.txt
```

**Filename Format**: Result tarballs use the format `{instance-group}_{instance-id}.tar.gz` where:
- `instance-group`: The HyperPod instance group name (e.g., `worker1`, `worker2`)
- `instance-id`: The EC2 instance ID (e.g., `i-0123456789abcdef0`)

### View Results

#### Quick Check with Helper Script

```bash
./check_results.sh my-bucket my-cluster 20260126_143022
```

This will show you:
- If the report exists
- Summary statistics
- Number of result files
- Troubleshooting tips if results are missing

#### Manual Download and Extract

```bash
# Download all results
aws s3 sync s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/results/ ./reports/

# Extract a specific report
tar -xzf reports/worker1_i-0123456789abcdef0.tar.gz

# View nvidia-smi output
cat hyperpod_report_worker1_i-0123456789abcdef0_20260126_143025/command_01_nvidia-smi.txt

# View EKS logs
ls hyperpod_report_worker1_i-0123456789abcdef0_20260126_143025/eks-logs/
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
        "s3:GetObject"
      ],
      "Resource": "*"
    }
  ]
}
```

### For the HyperPod Node IAM Role

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
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:UpdateInstanceInformation",
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    }
  ]
}
```

## Troubleshooting

### No Results in S3 Results Folder

If you see `collector_script.sh` and `summary.json` but no files in the `results/` folder:

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

## Limitations

- Requires SSM connectivity to all nodes
- Commands must complete within 5 minutes per node
- Large output files may take time to upload to S3
- Concurrent execution limited by `--max-workers` setting
- Nodes must have AWS CLI installed

## Technical Details

### Comparison with hyperpod_issue_report

**hyperpod_issue_report (Slurm-based)**:
- Uses SSH for connectivity
- Requires head node access
- Slurm-specific commands
- Direct file system access

**hyperpod_eks_issue_report (EKS-based)**:
- Uses SSM for connectivity
- No head node required
- Kubernetes-aware
- S3-based distribution and collection

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

- `hyperpod_run_on_multi_nodes`: Interactive command execution on multiple nodes
- `hyperpod_issue_report`: Slurm-based issue report collector for HyperPod Slurm clusters
- AWS EKS Log Collector: https://github.com/awslabs/amazon-eks-ami/blob/main/log-collector-script/linux/eks-log-collector.sh
