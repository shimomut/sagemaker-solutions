# Quick Start Guide

## Prerequisites

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

## Basic Usage

### 1. Collect nvidia-smi from all nodes

```bash
python hyperpod_eks_issue_report.py \
  --cluster my-hyperpod-cluster \
  --s3-bucket my-diagnostics-bucket \
  --command "nvidia-smi"
```

### 2. Using Makefile

```bash
# Collect nvidia-smi
make run-nvidia CLUSTER=my-cluster S3_BUCKET=my-bucket

# Collect system health
make run-system CLUSTER=my-cluster S3_BUCKET=my-bucket

# Collect Kubernetes status
make run-k8s CLUSTER=my-cluster S3_BUCKET=my-bucket
```

## What Happens

1. Script queries SageMaker API to get all nodes in your cluster
2. Generates a bash script with your commands
3. Uploads the script to S3
4. Executes the script on all nodes via SSM
5. Each node:
   - Downloads the script from S3
   - Runs all commands
   - Creates a tarball of results
   - Uploads to S3
6. Summary JSON is created with collection status

## View Results

Results are stored in S3:
```
s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/
├── collector_script.sh              # Single script (uses env vars)
├── summary.json
└── results/
    ├── worker1_i-0123456789abcdef0.tar.gz
    ├── worker1_i-0123456789abcdef1.tar.gz
    └── ...
```

**Note**: Result files use the format `{instance-group}_{instance-id}.tar.gz` (e.g., `worker1_i-0123456789abcdef0.tar.gz`). The collector script uses environment variables for instance identification.

### Quick Check with Helper Script

```bash
./check_results.sh my-bucket my-cluster 20260126_143022
```

This will show you:
- If the report exists
- Summary statistics
- Number of result files
- Troubleshooting tips if results are missing

### Manual Download and Extract

Download and extract:
```bash
# Download all results
aws s3 sync s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/results/ ./reports/

# Extract a specific report
tar -xzf reports/hyperpod_report_ip-10-0-1-100_20260126_143025.tar.gz

# View nvidia-smi output
cat hyperpod_report_ip-10-0-1-100_20260126_143025/command_01_nvidia-smi.txt
```

## Common Commands

### GPU Diagnostics
```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket my-bucket \
  --command "nvidia-smi" \
  --command "nvidia-smi -q"
```

### System Health
```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket my-bucket \
  --command "uptime" \
  --command "free -h" \
  --command "df -h"
```

### Target Specific Instance Group
```bash
python hyperpod_eks_issue_report.py \
  --cluster my-cluster \
  --s3-bucket my-bucket \
  --instance-group worker-group \
  --command "nvidia-smi"
```

## Troubleshooting

### No results in S3?

Check the summary.json:
```bash
aws s3 cp s3://my-bucket/hyperpod-issue-reports/my-cluster/20260126_143022/summary.json -
```

If `"Success": false`, look at the `"Error"` field. Common issues:
- Node IAM role missing S3 write permissions
- SSM command execution failures
- Script errors on nodes

Get detailed SSM output:
```bash
# Use CommandId from summary.json
aws ssm get-command-invocation --command-id <command-id> --instance-id <ssm-target>
```

### SSM Connection Issues
If nodes fail to respond, check:
```bash
# Verify SSM agent is running on nodes
aws ssm describe-instance-information

# Check IAM role has SSM permissions
aws iam get-role --role-name YourHyperPodNodeRole
```

### S3 Upload Issues
If uploads fail:
```bash
# Test S3 access from your machine
aws s3 ls s3://my-bucket/

# Verify node IAM role has S3 permissions
aws iam list-attached-role-policies --role-name YourHyperPodNodeRole
```

## Next Steps

- See [README.md](README.md) for detailed documentation
- See [examples.sh](examples.sh) for more usage examples
- Check IAM policy requirements in README.md
