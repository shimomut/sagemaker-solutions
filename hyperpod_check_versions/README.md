# HyperPod Version Checker

Comprehensive diagnostic script to investigate software component versions on HyperPod cluster instances. This tool helps determine appropriate versions for GDRCOPY, EFA, AWS OFI NCCL, NCCL, CUDA, and other critical components for distributed ML training.

## Overview

When troubleshooting NCCL performance issues or setting up distributed training environments, knowing the exact versions of all components is crucial. This script automatically detects and reports versions of:

- NVIDIA GPU drivers and CUDA toolkit
- NCCL (NVIDIA Collective Communications Library)
- EFA (Elastic Fabric Adapter) and libfabric
- AWS OFI NCCL plugin
- GDRCopy (GPU Direct RDMA Copy)
- MPI implementations
- Python and PyTorch
- Container runtime components

## Features

- Comprehensive version detection across multiple sources (libraries, headers, package managers)
- CUDA/driver compatibility analysis with recommendations
- Color-coded output for easy reading
- Saves detailed report to timestamped file
- Works on both HyperPod EKS and Slurm clusters
- Detects components from multiple installation locations

## Usage

### Basic Usage

Run the script directly on a HyperPod cluster node:

```bash
bash hyperpod_check_versions.sh
```

The script will:
1. Display results to stdout with color coding
2. Save a detailed report to `component_versions_<hostname>_<timestamp>.txt`

### On HyperPod EKS

Copy the script to a pod and execute:

```bash
# Copy to running pod
kubectl cp hyperpod_check_versions.sh <pod-name>:/tmp/

# Execute in pod
kubectl exec -it <pod-name> -- bash /tmp/hyperpod_check_versions.sh

# Retrieve the output file
kubectl cp <pod-name>:/tmp/component_versions_*.txt ./
```

### On HyperPod Slurm

Run directly on compute nodes via SSH or Slurm job:

```bash
# Via SSH
ssh <node-name> 'bash -s' < hyperpod_check_versions.sh

# Via Slurm job
srun --nodes=1 bash hyperpod_check_versions.sh
```

### Using SSM (for remote execution)

```bash
# Copy script to S3
aws s3 cp hyperpod_check_versions.sh s3://<bucket>/scripts/

# Execute via SSM on HyperPod instance
aws ssm send-command \
    --instance-ids <instance-id> \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["aws s3 cp s3://<bucket>/scripts/hyperpod_check_versions.sh /tmp/","bash /tmp/hyperpod_check_versions.sh"]'
```

## Output

### Console Output

The script provides color-coded sections:
- Blue: Section headers
- Green: Success messages and compatibility confirmations
- Yellow: Warnings or missing components
- Red: Errors (if any)

### Report File

A detailed text file is saved with the naming pattern:
```
component_versions_<hostname>_YYYYMMDD_HHMMSS.txt
```

The report includes:
- System information (OS, kernel, architecture)
- Detailed version information for each component
- Library and header file locations
- Package manager listings
- Environment variables
- Version summary with key components
- CUDA/driver compatibility analysis

## Key Sections in Report

### System Information
- Operating system and kernel version
- System architecture

### CUDA Information
- NVIDIA driver version
- Maximum supported CUDA version (from driver)
- Installed CUDA toolkit versions
- GPU information

### NCCL Information
- NCCL library versions (from filenames)
- NCCL header versions
- Package manager listings

### EFA Information
- EFA installer version
- Libfabric version
- EFA provider details
- Network device information

### AWS OFI NCCL Plugin
- Plugin version
- Library locations
- Package information

### GDRCopy Information
- GDRCopy version
- Kernel module status
- Library locations

### Version Summary
Extracted key versions in easy-to-parse format:
```
NVIDIA_GPU_DRIVER_VERSION: 535.104.05
MAX_SUPPORTED_CUDA_VERSION: 12.2
CUDA_TOOLKIT_VERSION: 12.1
NCCL_VERSION: v2.18.5-1
EFA_INSTALLER_VERSION: 1.29.1
AWS_OFI_NCCL_VERSION: v1.7.3
GDRCOPY_VERSION: v2.3.1
```

### CUDA/Driver Compatibility Analysis
Provides guidance on which CUDA versions are compatible with the installed driver:
- Driver 580+: CUDA 13.x, 12.x, 11.x
- Driver 570+: CUDA 12.8+ (Blackwell), 12.x, 11.x
- Driver 525+: CUDA 12.0-12.7, 11.x
- Driver 450+: CUDA 11.x

## Use Cases

### Troubleshooting NCCL Performance
When experiencing slow NCCL performance, check:
- EFA and AWS OFI NCCL plugin versions match
- GDRCopy is installed and kernel module loaded
- NCCL version is compatible with CUDA version

### Container Image Selection
Use the detected versions to select appropriate container images:
- Match CUDA version to driver compatibility
- Ensure NCCL version in container matches host EFA/OFI versions
- Verify PyTorch CUDA version compatibility

### Cluster Configuration Validation
Verify all nodes have consistent versions:
```bash
# Run on all nodes and compare
for node in node-{1..8}; do
    ssh $node 'bash -s' < hyperpod_check_versions.sh > ${node}_versions.txt
done
```

### Documentation and Support
Include the output file when:
- Opening support tickets
- Reporting performance issues
- Documenting cluster configurations
- Sharing environment details with team

## Requirements

- Bash shell
- Standard Linux utilities (grep, sed, awk, find)
- Access to system directories (/usr, /opt, /sys)
- Optional: nvidia-smi, nvcc, fi_info for detailed information

## Notes

- The script uses `set -e` to exit on errors, but handles missing commands gracefully
- Some sections may show "not found" if components aren't installed - this is normal
- The script is read-only and makes no system modifications
- Color codes may not display correctly in all terminals (output file has plain text)

## Related Tools

- `nvidia-smi`: GPU and driver information
- `fi_info`: EFA and libfabric details
- `lsmod`: Kernel module status
- `dpkg -l` / `rpm -qa`: Package listings

## Troubleshooting

### Script fails with permission errors
Run with appropriate permissions or use sudo:
```bash
sudo bash hyperpod_check_versions.sh
```

### No CUDA information detected
Ensure NVIDIA drivers are installed and nvidia-smi is in PATH:
```bash
which nvidia-smi
/usr/bin/nvidia-smi --version
```

### EFA information missing
Verify EFA is installed:
```bash
ls -la /opt/amazon/efa/
fi_info -p efa
```

### Output file not created
Check write permissions in current directory:
```bash
touch test.txt && rm test.txt
```

## Version History

- Initial version: Comprehensive component detection for HyperPod clusters
