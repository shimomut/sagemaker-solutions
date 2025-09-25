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

### Basic Network Interface Management

Run the script with sudo privileges:

```bash
sudo python3 hyperpod_eks_netinf.py
```

### Connectivity Verification

After moving network interfaces, verify internet connectivity:

```bash
# Auto-detect and test recently moved interfaces
make verify-connectivity

# Test a specific interface
make verify-interface INTERFACE=eth2

# Complete workflow: move interface and verify connectivity (requires sudo)
make move-and-verify

# Diagnose TCP connectivity issues
make diagnose
make diagnose INTERFACE=enp75s0
```

### Manual Connectivity Testing

```bash
# Test auto-detected interface with verbose output
python3 verify_connectivity.py --verbose --save-results

# Test specific interface
python3 verify_connectivity.py --interface eth2 --verbose

# Save results to custom file
python3 verify_connectivity.py --output my_test_results.json
```

## What the Scripts Do

### Network Interface Manager (hyperpod_eks_netinf.py)

#### 1. Discovery Phase
- Executes `sudo ip netns exec default ip link` to list interfaces in default namespace
- Executes `sudo ip netns exec sagemaker_agent_namespace ip link` to list interfaces in sagemaker namespace
- Executes `ip route` to capture current routing table

#### 2. Analysis Phase
- Parses network interface information (name, state, MAC address)
- Identifies the first DOWN interface in sagemaker_agent_namespace
- Uses boto3 to query AWS EC2 API and match the interface MAC address to an ENI

#### 3. Confirmation Phase
- Displays detailed information about the selected interface and its ENI
- Shows interface name, MAC address, current state, and ENI details
- Asks for user confirmation before proceeding

#### 4. Configuration Phase (if confirmed)
- Moves the interface from sagemaker_agent_namespace to default namespace
- Assigns the ENI's private IP address with /16 subnet mask
- Brings the interface up
- Calculates appropriate route metric based on existing routing table
- Adds a default route via 10.1.0.1 with dynamically calculated metric

#### 5. Verification Phase
- Displays final `ip addr` output
- Displays final `ip link` output  
- Displays final `ip route` output

### Connectivity Verifier (verify_connectivity.py)

#### 1. Interface Detection
- Auto-detects recently moved network interfaces (prioritizes 10.1.x.x addresses)
- Can target specific interfaces when specified
- Validates interface state and IP configuration

#### 2. DNS Resolution Tests
- Tests DNS resolution for common domains (google.com, amazon.com, github.com)
- Measures resolution time and validates responses

#### 3. Ping Connectivity Tests
- Tests ICMP connectivity to multiple hosts (8.8.8.8, 1.1.1.1, amazon.com, google.com, github.com)
- Measures packet loss and round-trip times
- Uses interface-specific routing

#### 4. TCP Connection Tests
- Tests TCP connectivity on ports 80, 443, and 53
- Uses SO_BINDTODEVICE socket option for reliable interface binding
- Falls back to IP binding if SO_BINDTODEVICE requires root privileges
- Measures connection establishment time
- Provides detailed error messages for connection failures

#### 5. HTTP Connectivity Tests
- Tests HTTP/HTTPS requests using curl with interface binding
- Validates response codes and measures request times
- Tests multiple endpoints for comprehensive validation

#### 6. Results Analysis
- Calculates overall success rate (70% threshold for pass/fail)
- Generates detailed JSON reports with timestamps
- Provides summary statistics and recommendations

## Connectivity Verification Features

### Test Categories

1. **DNS Resolution Tests**
   - Validates DNS functionality for common domains
   - Measures resolution time and success rate

2. **Ping Connectivity Tests**
   - Tests ICMP reachability to multiple hosts
   - Measures packet loss and latency
   - Uses interface-specific routing

3. **TCP Connection Tests**
   - Tests TCP connectivity on standard ports (80, 443, 53)
   - Validates socket binding to interface IP
   - Measures connection establishment time

4. **HTTP Connectivity Tests**
   - Tests actual HTTP/HTTPS requests
   - Validates response codes and content delivery
   - Uses curl with interface binding

### Success Criteria

- **DNS Tests**: All domains should resolve successfully
- **Ping Tests**: <10% packet loss acceptable
- **TCP Tests**: Connections should establish within 5 seconds
- **HTTP Tests**: Should receive 2xx/3xx response codes
- **Overall**: 70% success rate required for PASS status

### Output Formats

- **Console**: Real-time progress with colored status indicators (red for errors, green for success)
- **JSON**: Detailed results with timestamps and metrics
- **Summary**: Pass/fail status with success rate percentage

### Diagnostic Features

- **TCP Connection Diagnostics**: Automatic fallback from SO_BINDTODEVICE to IP binding
- **Detailed Error Messages**: Human-readable explanations for connection failures
- **Interface Validation**: Comprehensive interface state and configuration checks
- **Diagnostic Script**: Separate diagnostic tool for troubleshooting TCP connectivity issues

## Example Output

### Network Interface Management

```
HyperPod EKS Network Interface Manager
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

### Connectivity Verification

```
HyperPod EKS Network Interface Connectivity Verifier
============================================================

Testing connectivity for interface: eth2
Interface IP: 10.1.45.123
------------------------------------------------------------

1. DNS Resolution Tests
------------------------------
[2024-09-25 14:30:15] SUCCESS: ✓ DNS google.com: Resolved to ['142.250.191.14'] in 12.3ms
[2024-09-25 14:30:15] SUCCESS: ✓ DNS amazon.com: Resolved to ['205.251.242.103'] in 8.7ms
[2024-09-25 14:30:15] SUCCESS: ✓ DNS github.com: Resolved to ['140.82.113.4'] in 15.2ms

2. Ping Connectivity Tests
------------------------------
[2024-09-25 14:30:16] SUCCESS: ✓ Ping to 8.8.8.8: 0.0% loss, avg 2.1ms
[2024-09-25 14:30:17] SUCCESS: ✓ Ping to 1.1.1.1: 0.0% loss, avg 3.4ms
[2024-09-25 14:30:18] SUCCESS: ✓ Ping to amazon.com: 0.0% loss, avg 12.7ms
[2024-09-25 14:30:19] SUCCESS: ✓ Ping to google.com: 0.0% loss, avg 8.9ms
[2024-09-25 14:30:20] SUCCESS: ✓ Ping to github.com: 0.0% loss, avg 15.3ms

3. TCP Connection Tests
------------------------------
[2024-09-25 14:30:21] SUCCESS: ✓ TCP 8.8.8.8:53: Connected in 2.1ms
[2024-09-25 14:30:21] SUCCESS: ✓ TCP 8.8.8.8:80: Connected in 3.4ms
[2024-09-25 14:30:22] SUCCESS: ✓ TCP google.com:443: Connected in 12.7ms
[2024-09-25 14:30:23] SUCCESS: ✓ TCP amazon.com:443: Connected in 18.9ms

4. HTTP Connectivity Tests
------------------------------
[2024-09-25 14:30:24] SUCCESS: ✓ HTTP http://google.com: 301 in 45.2ms
[2024-09-25 14:30:25] SUCCESS: ✓ HTTP https://amazon.com: 200 in 67.8ms
[2024-09-25 14:30:26] SUCCESS: ✓ HTTP https://github.com: 200 in 89.1ms

============================================================
CONNECTIVITY TEST SUMMARY
============================================================
Interface: eth2 (10.1.45.123)
Total Tests: 20
Passed: 20
Failed: 0
Success Rate: 100.0%
Overall Result: ✓ PASS
============================================================
```

## Commands Executed

### Network Interface Manager Commands

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
   sudo ip route add default via 10.1.0.1 dev {interface-name} metric {calculated-metric}
   ```

3. **Verification Commands**:
   ```bash
   ip addr
   ip link
   ip route
   ```

### Connectivity Verifier Commands

1. **Interface Discovery**:
   ```bash
   ip -j addr show
   ```

2. **Connectivity Tests**:
   ```bash
   ping -I {interface} -c 3 -W 5 {host}
   curl --interface {interface} --connect-timeout 10 --max-time 10 -s -o /dev/null -w '%{http_code},%{time_total}' {url}
   ```

3. **Make Targets**:
   ```bash
   make verify-connectivity              # Auto-detect and test interfaces
   make verify-interface INTERFACE=eth2  # Test specific interface
   make move-and-verify                  # Complete workflow (requires sudo)
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

## Route Metric Calculation

The script dynamically calculates the appropriate metric for the new default route to avoid conflicts with existing routes:

### Calculation Logic

1. **Analyze Existing Routes**: Scans current routing table for existing default routes and their metrics
2. **Metric Selection**:
   - If no existing metrics found: Uses metric 100
   - If existing metrics are low (< 50): Uses metric 100 for clear secondary priority
   - If higher metrics exist: Uses (max_existing_metric + 100)
   - Maximum cap: 1000 to prevent excessively high values

### Examples

```bash
# Scenario 1: No existing default routes
# Result: metric 100

# Scenario 2: Existing default route with metric 0
# Result: metric 100 (ensures secondary priority)

# Scenario 3: Existing routes with metrics 0, 200, 300
# Result: metric 400 (300 + 100)

# Scenario 4: High existing metrics (e.g., 950)
# Result: metric 1000 (capped at maximum)
```

This ensures the moved interface route has appropriate priority without disrupting existing network connectivity.

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