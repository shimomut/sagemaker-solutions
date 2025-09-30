# HyperPod Multi-Node Command Runner

A utility tool to execute commands on all nodes in a HyperPod cluster using AWS Systems Manager (SSM) sessions.

## Features

- Lists all nodes in a HyperPod cluster using boto3
- Executes commands on multiple nodes simultaneously via SSM sessions
- Real-time output display from all nodes
- Interactive command input loop
- Handles node connectivity and session management

## Prerequisites

- AWS CLI configured with appropriate permissions
- SSM permissions for the HyperPod cluster nodes
- Python 3.x with required dependencies

## Usage

```bash
python main.py
```

The tool will:
1. Prompt for the HyperPod cluster name
2. List all available nodes in the cluster
3. Enter interactive mode where you can input commands
4. Execute commands on all nodes simultaneously
5. Display output from each node
6. Return to command prompt when execution completes

## Commands

- Enter any shell command to execute on all nodes
- Type `exit` or `quit` to exit the tool
- Use `Ctrl+C` to interrupt current execution

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