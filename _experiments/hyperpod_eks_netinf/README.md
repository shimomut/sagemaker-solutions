# HyperPod EKS Network Interface Script

An experimental script for moving network interfaces between namespaces on Amazon Linux 2023 (AL2023) in HyperPod EKS environments.

## Overview

This script moves network interfaces from the `sagemaker_agent_namespace` to the `default` namespace and configures them properly. It handles network interface operations that are common in HyperPod EKS cluster environments.

## Features

- **Namespace Discovery**: Automatically discovers network interfaces in both default and sagemaker_agent_namespace
- **Route Table Analysis**: Captures and analyzes the current IP routing configuration
- **ENI Integration**: Uses AWS EC2 API to match network interfaces with their corresponding ENIs
- **Interactive Confirmation**: Asks for user confirmation before making changes
- **Automated Configuration**: Handles IP assignment, interface activation, and route configuration
- **Verification**: Provides comprehensive verification of the final configuration

## Prerequisites

- Amazon Linux 2023 (AL2023)
- Python 3.9+
- Root/sudo privileges
- AWS credentials configured (IAM role or credentials file)
- Required IAM permissions:
  - `ec2:DescribeNetworkInterfaces`

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure the script has execute permissions:
```bash
chmod +x hyperpod_eks_netinf.py
```

## Usage

Run the script with sudo privileges:

```bash
sudo python3 hyperpod_eks_netinf.py
```

## What the Script Does

### 1. Discovery Phase
- Executes `sudo ip netns exec default ip link` to list interfaces in default namespace
- Executes `sudo ip netns exec sagemaker_agent_namespace ip link` to list interfaces in sagemaker namespace
- Executes `ip route` to capture current routing table

### 2. Analysis Phase
- Parses network interface information (name, state, MAC address)
- Identifies the first DOWN interface in sagemaker_agent_namespace
- Uses boto3 to query AWS EC2 API and match the interface MAC address to an ENI

### 3. Confirmation Phase
- Displays detailed information about the selected interface and its ENI
- Shows interface name, MAC address, current state, and ENI details
- Asks for user confirmation before proceeding

### 4. Configuration Phase (if confirmed)
- Moves the interface from sagemaker_agent_namespace to default namespace
- Assigns the ENI's private IP address with /16 subnet mask
- Brings the interface up
- Adds a default route via 10.1.0.1 with metric 400

### 5. Verification Phase
- Displays final `ip addr` output
- Displays final `ip link` output  
- Displays final `ip route` output

## Example Output

```
HyperPod EKS Network Interface Script
==================================================
Getting network interfaces in default namespace...
Found 2 interfaces in default namespace
Getting network interfaces in sagemaker_agent_namespace...
Found 3 interfaces in sagemaker_agent_namespace
Getting current IP route table...
Found 5 routes in route table
Found DOWN interface: eth2

============================================================
NETWORK INTERFACE DETAILS
============================================================
Interface Name: eth2
MAC Address: 02:34:56:78:9a:bc
Current State: DOWN

ENI Details:
  ENI ID: eni-0123456789abcdef0
  Private IP: 10.1.45.123
  Subnet ID: subnet-0123456789abcdef0
  VPC ID: vpc-0123456789abcdef0
============================================================

Do you want to proceed with moving this interface? (yes/no): yes

Moving interface eth2 to default namespace...
Successfully moved eth2 to default namespace
Assigning IP address 10.1.45.123/16 to eth2...
Successfully assigned IP address to eth2
Bringing interface eth2 up...
Successfully brought eth2 up
Adding default route via eth2...
Successfully added default route via eth2

============================================================
VERIFICATION - Final Configuration
============================================================
[Verification output follows...]
```

## Commands Executed

The script executes the following system commands:

1. **Discovery Commands**:
   ```bash
   sudo ip netns exec default ip link
   sudo ip netns exec sagemaker_agent_namespace ip link
   ip route
   ```

2. **Configuration Commands** (after confirmation):
   ```bash
   sudo ip netns exec sagemaker_agent_namespace ip link set {interface-name} netns default
   sudo ip addr add {ipaddr}/16 brd 10.1.255.255 dev {interface-name}
   sudo ip link set {interface-name} up
   sudo ip route add default via 10.1.0.1 dev {interface-name} metric 400
   ```

3. **Verification Commands**:
   ```bash
   ip addr
   ip link
   ip route
   ```

## Error Handling

- Command timeouts (30 second limit)
- Network namespace access errors
- AWS API errors
- Invalid interface states
- Missing ENI information
- User cancellation

## Security Considerations

- Requires sudo privileges for network namespace operations
- Uses AWS credentials for EC2 API access
- Modifies system network configuration
- Interactive confirmation prevents accidental changes

## Limitations

- Only works on Amazon Linux 2023
- Requires specific network namespace structure
- Assumes 10.1.0.0/16 subnet configuration
- Only processes the first DOWN interface found

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure script is run with sudo
2. **Namespace Not Found**: Verify sagemaker_agent_namespace exists
3. **AWS Credentials**: Ensure proper IAM role or credentials are configured
4. **No DOWN Interfaces**: All interfaces in sagemaker namespace are already UP

### Debug Mode

Add debug output by modifying the script to include verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

This is an experimental solution. When contributing:

1. Test thoroughly on AL2023 systems
2. Ensure backward compatibility
3. Add appropriate error handling
4. Update documentation

## License

This solution is provided as-is for experimental use in HyperPod EKS environments.