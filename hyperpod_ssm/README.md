# HyperPod SSM Interactive Shell

A utility tool that helps with SSM login to HyperPod nodes and provides an interactive shell for running commands.

## Features

- Interactive SSM session to HyperPod nodes
- Support for both command-line arguments and interactive prompts
- Cluster discovery and node selection
- Instance group filtering
- Real-time command execution with proper output handling
- AL2023 compatibility with improved prompt detection

## Usage

### Interactive Mode (Recommended)
```bash
python hyperpod_ssm.py
```

The tool will prompt you for:
1. Cluster name
2. Instance group (optional)
3. Specific instance ID (optional)

### Command Line Mode
```bash
# Specify all parameters
python hyperpod_ssm.py --cluster my-cluster --instance-group worker-group --instance-id i-1234567890abcdef0

# Specify cluster only (will prompt for instance selection)
python hyperpod_ssm.py --cluster my-cluster

# List available clusters and nodes
python hyperpod_ssm.py --list-clusters
python hyperpod_ssm.py --cluster my-cluster --list-nodes
```

### Options

- `--cluster, -c`: HyperPod cluster name
- `--instance-group, -g`: Instance group name (optional)
- `--instance-id, -i`: Specific instance ID to connect to
- `--list-clusters`: List all available HyperPod clusters
- `--list-nodes`: List all nodes in the specified cluster
- `--debug, -d`: Enable debug mode for troubleshooting
- `--help, -h`: Show help message

## Interactive Commands

Once connected to a node, you can use these special commands:

- `exit` or `quit`: Exit the SSM session
- `help`: Show available commands
- `debug`: Toggle debug mode
- `reconnect`: Reconnect to the same node
- `switch`: Switch to a different node
- Any other command: Execute directly on the remote node

## Examples

### Connect to a specific node
```bash
python hyperpod_ssm.py --cluster my-hyperpod-cluster --instance-id i-1234567890abcdef0
```

### Browse and select interactively
```bash
python hyperpod_ssm.py --cluster my-hyperpod-cluster
# Will show available instance groups and nodes for selection
```

### List all nodes in a cluster
```bash
python hyperpod_ssm.py --cluster my-hyperpod-cluster --list-nodes
```

## Requirements

- AWS CLI configured with appropriate permissions
- Python 3.6+
- Required Python packages: boto3, pexpect
- SSM permissions for HyperPod cluster access

## Troubleshooting

### SSM Connection Issues
1. Ensure SSM Agent is running: `sudo systemctl status amazon-ssm-agent`
2. Check SSM Agent logs: `sudo journalctl -u amazon-ssm-agent -f`
3. Verify IAM role has `AmazonSSMManagedInstanceCore` policy
4. Check security groups allow SSM traffic

### AL2023 Specific Issues
- Use `--debug` flag to see detailed connection information
- The tool automatically handles AL2023 prompt variations
- If connection hangs, try reconnecting or switching nodes

## Notes

- This tool uses the HyperPod SSM target format: `sagemaker-cluster:{cluster-id}_{instance-group-name}-{instance-id}`
- Sessions are automatically cleaned up on exit
- The tool supports both HyperPod EKS and Slurm clusters
- Interactive mode provides the best user experience for exploration and debugging