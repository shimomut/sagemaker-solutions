# HyperPod EKS Better Lifecycle Scripts

This experiment improves the lifecycle script architecture for HyperPod EKS clusters by separating the bootstrap logic from the main provisioning logic.

## Overview

Traditional HyperPod lifecycle scripts combine logging setup, error handling, and business logic in a single file. This experiment splits the responsibilities into two scripts:

- **Bootstrap Script** (`on_create.sh`): Handles logging setup, error handling, and script orchestration
- **Main Script** (`on_create_main.sh`): Contains the actual provisioning logic

## Architecture

### Bootstrap Script (`on_create.sh`)
- Sets up structured logging to `/var/log/provision/provisioning.log`
- Provides consistent log formatting with timestamps
- Handles script execution flow and error propagation
- Ensures proper log synchronization with `sync` calls

### Main Script (`on_create_main.sh`)
- Contains the core provisioning logic
- Configures containerd data root for secondary EBS volumes
- Handles OS-specific configuration (Amazon Linux 2 vs 2023)
- Manages containerd runtime configuration for GPU workloads

## Key Features

### Improved Logging
- Centralized log file at `/var/log/provision/provisioning.log`
- Structured logging with clear start/stop markers
- Real-time log output with `stdbuf` for immediate visibility
- Proper log synchronization to prevent data loss

### OS Version Detection
- Reliable OS version detection using `/etc/os-release`
- Separate handling for Amazon Linux 2 and Amazon Linux 2023
- Graceful handling of unsupported OS versions

### Configurable Data Path
- **Flexible disk selection**: Choose between `/opt/sagemaker` and `/opt/dlami/nvme` via `DISK_FOR_CONTAINERD_KUBELET` variable
- **Single configuration point**: Change one variable to switch storage locations
- **Clear naming**: Descriptive variable name indicates purpose for both containerd and kubelet data

### Robust File Operations
- **Safe kubelet migration**: Checks for existing files before attempting to move them
- **Empty directory handling**: Gracefully handles empty `/var/lib/kubelet` directories
- **Error prevention**: Avoids script failures when directories are empty

### Containerd Configuration
- **Amazon Linux 2**: Direct modification of existing config file using `sed`
- **Amazon Linux 2023**: Complete custom configuration with systemd overrides
- GPU runtime support with nvidia-container-runtime
- Proper cleanup of incompatible data between OS versions

## Usage

Deploy this lifecycle script configuration in your HyperPod EKS cluster provisioning parameters:

```json
{
  "provisioning_parameters": {
    "version": "1.0.0",
    "node_recovery": "Automatic",
    "cluster_type": "EKS",
    "lifecycle_scripts": {
      "on_create": "s3://your-bucket/path/to/on_create.sh"
    }
  }
}
```

## Benefits

1. **Separation of Concerns**: Bootstrap logic is separate from business logic
2. **Better Debugging**: Clear logging structure makes troubleshooting easier
3. **Maintainability**: Main script focuses purely on provisioning tasks
4. **Reusability**: Bootstrap pattern can be reused across different lifecycle scripts
5. **Reliability**: Proper error handling and log synchronization
6. **Flexibility**: Easy configuration switching between different storage locations
7. **Robustness**: Safe file operations that handle edge cases gracefully

## File Structure

```
hyperpod_eks_better_lcs/
├── README.md              # This documentation
├── on_create.sh          # Bootstrap script with logging setup
└── on_create_main.sh     # Main provisioning logic
```

## Implementation Details

### Configurable Storage Location
The script uses the `DISK_FOR_CONTAINERD_KUBELET` variable to determine where to store containerd and kubelet data:

```bash
# Configuration: Choose data path for containerd and kubelet
# Options: "/opt/sagemaker" or "/opt/dlami/nvme"
DISK_FOR_CONTAINERD_KUBELET="/opt/sagemaker"
```

To use NVMe storage instead, simply change to:
```bash
DISK_FOR_CONTAINERD_KUBELET="/opt/dlami/nvme"
```

### Containerd Data Root Configuration
The script automatically detects if the configured secondary EBS volume is mounted and configures containerd to use it for container storage, providing better performance and storage capacity for ML workloads.

### GPU Runtime Support
Includes proper configuration for nvidia-container-runtime to support GPU-accelerated containers in the HyperPod EKS cluster.

### Cross-OS Compatibility
Handles differences between Amazon Linux 2 and Amazon Linux 2023, including:
- Different containerd configuration file locations
- Systemd service override requirements
- Data directory compatibility issues

## Recent Improvements

### v1.1 - Enhanced Configuration and Robustness
- **Configurable storage path**: Added `DISK_FOR_CONTAINERD_KUBELET` variable for flexible disk selection
- **Improved error handling**: Safe kubelet file migration that handles empty directories
- **Better variable naming**: More descriptive variable names for clarity
- **Enhanced logging**: Added configuration logging for better debugging

## Future Enhancements

- Add support for additional lifecycle events (on_update, on_delete)
- Implement configuration validation for storage paths
- Add metrics collection for provisioning performance
- Support for custom containerd plugins
- Auto-detection of optimal storage location