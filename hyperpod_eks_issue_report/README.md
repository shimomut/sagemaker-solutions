# HyperPod EKS Issue Report Collector

A utility to collect diagnostic logs and configurations from multiple HyperPod EKS nodes. The tool downloads a collection script from S3, executes it on all specified nodes via SSM, and uploads the results back to S3.

## Features

- Collects diagnostic information from all nodes or specific instance groups
- Downloads collection script from S3 to each node
- Executes multiple commands on each node
- Uploads individual node reports to S3 as compressed tarballs
- Generates a summary JSON with collection status
- Concurrent execution across multiple nodes
- Built on top of HyperPod SSM connectivity

## Prerequisites

- AWS CLI configured with appropriate permissions
- SSM permissions for HyperPod cluster nodes
- S3 bucket for storing collection scripts and results
- Python 3.x with boto3 and pexpect
- IAM permissions:
  - `sagemaker:DescribeCluster`
  - `sagemaker:ListClusterNodes`
  - `ssm:StartSession`
  - `s3:PutObject`
  - `s3:GetObject`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage - Collect nvidia-smi from all nodes

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --command "nvidia-smi"
```

### Collect Multiple Commands

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --command "nvidia-smi" \
  --command "df -h" \
  --command "free -h" \
  --command "uptime" \
  --command "kubectl get nodes"
```

### Target Specific Instance Group

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --instance-group worker-group \
  --command "nvidia-smi"
```

### Custom S3 Prefix

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --s3-prefix diagnostics/gpu-issues \
  --command "nvidia-smi" \
  --command "nvidia-smi -q"
```

### Debug Mode

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --command "nvidia-smi" \
  --debug
```

## Command Line Options

- `--cluster, -c`: HyperPod cluster name (required)
- `--s3-bucket, -b`: S3 bucket for storing reports (required)
- `--s3-prefix, -p`: S3 prefix for reports (default: hyperpod-issue-reports)
- `--command, -cmd`: Command to execute on nodes (can be specified multiple times, required)
- `--instance-group, -g`: Target specific instance group only
- `--max-workers, -w`: Maximum concurrent workers (default: 10)
- `--debug, -d`: Enable debug mode

## How It Works

1. **Cluster Discovery**: Queries SageMaker API to get all nodes in the cluster
2. **Script Generation**: Creates a bash script that will run the specified commands
3. **Script Upload**: Uploads the collection script to S3
4. **Parallel Execution**: Uses SSM interactive sessions with `pexpect` to execute the script on all nodes concurrently
   - **Important**: Uses HyperPod SSM target format: `sagemaker-cluster:{cluster-id}_{instance-group}-{instance-id}`
   - Interactive session approach (like `hyperpod_run_on_multi_nodes`) is required for HyperPod nodes
5. **Result Collection**: Each node:
   - Downloads the script from S3
   - Executes all specified commands
   - Captures output to individual files
   - Creates a tarball of all results
   - Uploads the tarball to S3
6. **Summary Generation**: Creates a JSON summary with collection status

## Output Structure

Results are stored in S3 with the following structure:

```
s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/
├── collector_script.sh              # The collection script
├── summary.json                     # Summary of collection status
└── results/
    ├── hyperpod_report_ip-10-0-1-100_20260126_143025.tar.gz
    ├── hyperpod_report_ip-10-0-1-101_20260126_143026.tar.gz
    └── hyperpod_report_ip-10-0-1-102_20260126_143027.tar.gz
```

Each tarball contains:

```
hyperpod_report_ip-10-0-1-100_20260126_143025/
├── hostname.txt
├── timestamp.txt
├── command_01_nvidia-smi.txt
├── command_02_df_-h.txt
└── command_03_free_-h.txt
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

## Common Use Cases

### GPU Diagnostics

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket diagnostics \
  --command "nvidia-smi" \
  --command "nvidia-smi -q" \
  --command "nvidia-smi topo -m"
```

### System Health Check

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket diagnostics \
  --command "uptime" \
  --command "free -h" \
  --command "df -h" \
  --command "top -bn1 | head -20"
```

### Kubernetes Status

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket diagnostics \
  --command "kubectl get nodes" \
  --command "kubectl get pods --all-namespaces" \
  --command "kubectl top nodes"
```

### Network Diagnostics

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket diagnostics \
  --command "ip addr show" \
  --command "ip route show" \
  --command "ss -tulpn"
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
- `"CommandId"` can be used to get detailed SSM logs

2. **Get detailed SSM command output**:
```bash
# Using CommandId from summary.json
aws ssm get-command-invocation \
  --command-id <command-id> \
  --instance-id <ssm-target-from-summary>
```

3. **Common causes**:
   - Node IAM role missing S3 write permissions
   - Script execution errors (check StandardErrorContent in SSM)
   - Network connectivity issues to S3
   - Insufficient disk space on nodes

4. **Verify node IAM role** has required permissions:
```bash
# Check if role has S3 permissions
aws iam get-role --role-name YourHyperPodNodeRole
aws iam list-attached-role-policies --role-name YourHyperPodNodeRole
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
4. Use `--debug` flag for detailed error messages

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

## Limitations

- Requires SSM connectivity to all nodes
- Commands must complete within 5 minutes per node
- Large output files may take time to upload to S3
- Concurrent execution limited by `--max-workers` setting
- Nodes must have AWS CLI installed

## Related Tools

- `hyperpod_run_on_multi_nodes`: Interactive command execution on multiple nodes
- `hyperpod_issue_report`: Slurm-based issue report collector for HyperPod Slurm clusters
