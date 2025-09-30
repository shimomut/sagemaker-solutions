# HyperPod Multi-Node Command Runner

A utility tool to execute commands on all nodes in a HyperPod cluster using AWS Systems Manager (SSM) sessions.

## Features

- Lists all nodes in a HyperPod cluster using SageMaker APIs
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
python main.py
```

### Command Line Mode

```bash
# Specify cluster and run single command
python main.py --cluster my-cluster --command "uptime"

# Enable debug mode
python main.py --cluster my-cluster --debug

# Test connectivity to specific node
python main.py --test-node i-1234567890abcdef0
```

### Options

- `--cluster, -c`: Specify HyperPod cluster name
- `--command`: Execute single command (non-interactive mode)
- `--debug, -d`: Enable debug mode for troubleshooting
- `--test-node, -t`: Test SSM connectivity to specific instance ID

## Interactive Commands

- Enter any shell command to execute on all nodes
- `test` - Run a simple connectivity test on all nodes
- `help` - Show available commands
- `exit`, `quit`, or `q` - Exit the tool
- Use `Ctrl+C` to interrupt current execution

## Key Improvements

This version includes several improvements over the basic implementation:

1. **Custom Prompt Handling**: Uses a custom prompt (`pexpect# `) for reliable output parsing, eliminating issues with varying shell prompts
2. **Better Session Management**: Improved pexpect session handling with proper cleanup
3. **Enhanced Error Handling**: More robust error detection and reporting
4. **Debug Mode**: Detailed logging for troubleshooting connectivity issues
5. **Command Line Interface**: Support for non-interactive usage
6. **Cleaner Output**: Better separation of command output from shell prompts

## Example

```
Enter HyperPod cluster name: my-hyperpod-cluster
Found 4 nodes in cluster: my-hyperpod-cluster
- i-1234567890abcdef0 (controller-machine-group-1)
- i-0987654321fedcba0 (worker-machine-group-1)
- i-abcdef1234567890 (worker-machine-group-2)
- i-fedcba0987654321 (worker-machine-group-3)

Enter command to run on all nodes (or 'exit' to quit): uptime
[i-1234567890abcdef0] 14:30:25 up 2 days, 3:45, 0 users, load average: 0.15, 0.10, 0.05
[i-0987654321fedcba0] 14:30:25 up 2 days, 3:45, 0 users, load average: 1.25, 1.10, 1.05
[i-abcdef1234567890] 14:30:25 up 2 days, 3:45, 0 users, load average: 0.85, 0.90, 0.95
[i-fedcba0987654321] 14:30:25 up 2 days, 3:45, 0 users, load average: 2.15, 2.10, 2.05

Enter command to run on all nodes (or 'exit' to quit): 
```

## Requirements

See `requirements.txt` for Python dependencies.