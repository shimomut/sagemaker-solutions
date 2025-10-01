# HyperPod Multi-Node Command Runner

A utility tool to execute commands on all nodes or specific instance groups in a HyperPod cluster using AWS Systems Manager (SSM) sessions.

## Features

- Lists all nodes in a HyperPod cluster using SageMaker APIs with pagination support
- **Instance group targeting** - Execute commands on specific instance groups or all nodes
- **Interactive instance group selection** - Choose target groups at startup
- Executes commands on multiple nodes simultaneously via SSM sessions
- **Improved output parsing** with custom prompts for reliable command execution
- Real-time output display from all nodes with clean formatting
- Interactive command input loop with built-in help
- Robust session management and error handling
- Debug mode for troubleshooting connectivity issues
- Command-line interface for non-interactive usage

## Prerequisites

- AWS CLI configured with appropriate permissions
- SSM permissions for the HyperPod cluster nodes
- Python 3.x with required dependencies (see `requirements.txt`)

## Usage

### Interactive Mode

```bash
python hyperpod_run_on_multi_nodes.py
```

The tool will prompt you to:
1. Enter the HyperPod cluster name
2. Select an instance group (or choose "All groups" to target all nodes)
3. Execute commands on the selected target

### Command Line Mode

```bash
# Specify cluster and run single command on all nodes
python hyperpod_run_on_multi_nodes.py --cluster my-cluster --command "uptime"

# Target specific instance group
python hyperpod_run_on_multi_nodes.py --cluster my-cluster --instance-group worker-group --command "uptime"

# List available instance groups
python hyperpod_run_on_multi_nodes.py --cluster my-cluster --list-groups

# Interactive mode with pre-selected instance group
python hyperpod_run_on_multi_nodes.py --cluster my-cluster --instance-group worker-group

# Enable debug mode
python hyperpod_run_on_multi_nodes.py --cluster my-cluster --debug

# Test connectivity to specific node
python hyperpod_run_on_multi_nodes.py --test-node i-1234567890abcdef0
```

### Options

- `--cluster, -c`: Specify HyperPod cluster name
- `--command`: Execute single command (non-interactive mode)
- `--instance-group, -g`: Target specific instance group only
- `--list-groups`: List all instance groups and exit
- `--debug, -d`: Enable debug mode for troubleshooting
- `--test-node, -t`: Test SSM connectivity to specific instance ID

## Interactive Commands

- Enter any shell command to execute on the selected target (instance group or all nodes)
- `test` - Run a simple connectivity test on the selected target
- `help` - Show available commands
- `debug` - Toggle debug mode for troubleshooting
- `al2023` - Show AL2023 specific troubleshooting tips
- `exit`, `quit`, or `q` - Exit the tool
- Use `Ctrl+C` to interrupt current execution

## Key Features

This tool provides comprehensive functionality for managing HyperPod clusters:

1. **Instance Group Targeting**: Select specific instance groups (controller, worker, etc.) or run on all nodes
2. **Pagination Support**: Handles large clusters with multiple pages of nodes automatically
3. **Custom Prompt Handling**: Uses a custom prompt (`PEXPECT_READY# `) for reliable output parsing
4. **Interactive Group Selection**: User-friendly menu to choose target instance groups
5. **Better Session Management**: Improved pexpect session handling with proper cleanup
6. **Enhanced Error Handling**: More robust error detection and reporting with HyperPod-specific SSM targets
7. **Debug Mode**: Detailed logging for troubleshooting connectivity issues
8. **Command Line Interface**: Support for non-interactive usage and automation
9. **Cleaner Output**: Better separation of command output from shell prompts with node group identification

## Example Usage

### Interactive Mode with Instance Group Selection

```
$ python hyperpod_run_on_multi_nodes.py

HyperPod Multi-Node Command Runner
========================================
Enter HyperPod cluster name: my-hyperpod-cluster

Describing cluster: my-hyperpod-cluster
Cluster status: InService
Found 8 nodes in cluster: my-hyperpod-cluster
Instance groups: controller-group(2), worker-group(6)

Instance Group Selection
=========================
Available instance groups:
0. All groups (run on all nodes)
1. controller-group (2 nodes)
2. worker-group (6 nodes)

Select instance group (0-2): 2
Selected: worker-group (6 nodes)

Testing SSM connectivity...
✓ SSM connectivity test passed: SSM test successful from ip-10-0-1-100

Ready to execute commands on instance group 'worker-group'
Use 'exit' to quit the tool.

[worker-group] Enter command: uptime

Executing command on 6 nodes in instance group 'worker-group': uptime
------------------------------------------------------------
[✓] i-0987654321fedcba0 (worker-group):
    14:30:25 up 2 days, 3:45, 0 users, load average: 1.25, 1.10, 1.05

[✓] i-abcdef1234567890 (worker-group):
    14:30:25 up 2 days, 3:45, 0 users, load average: 0.85, 0.90, 0.95

[✓] i-fedcba0987654321 (worker-group):
    14:30:25 up 2 days, 3:45, 0 users, load average: 2.15, 2.10, 2.05
...
------------------------------------------------------------
Command execution completed on all nodes.

[worker-group] Enter command: exit
Goodbye!
```

### Command Line Usage

```bash
# List instance groups
$ python hyperpod_run_on_multi_nodes.py --cluster my-cluster --list-groups
Instance Groups:
  - controller-group: 2 nodes
  - worker-group: 6 nodes

# Run command on specific instance group
$ python hyperpod_run_on_multi_nodes.py --cluster my-cluster --instance-group worker-group --command "nvidia-smi"

# Run on all nodes
$ python hyperpod_run_on_multi_nodes.py --cluster my-cluster --command "df -h"
```

## Requirements

See `requirements.txt` for Python dependencies.