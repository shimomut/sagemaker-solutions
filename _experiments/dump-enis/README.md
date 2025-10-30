# ENI Dump Utility

A utility script to dump all Elastic Network Interfaces (ENIs) under a specific VPC to a JSON file.

## Overview

This script fetches all ENIs within a specified VPC and exports comprehensive information about each interface to a structured JSON file. It's particularly useful for network analysis, troubleshooting, and inventory management.

## Features

- Dumps all ENIs from a specified VPC
- Comprehensive ENI information including:
  - Basic interface details (ID, description, status, type)
  - Network configuration (subnet, VPC, AZ, IP addresses)
  - Security groups and attachment information
  - All tags with special handling for Kubernetes/EKS tags
- JSON output with metadata and summary statistics
- Support for pretty-printed JSON
- Pagination handling for large numbers of ENIs

## Usage

### Basic Usage

```bash
# Output pretty JSON to stdout
python dump-enis.py --vpc-id vpc-12345678

# Save to file
python dump-enis.py --vpc-id vpc-12345678 > enis.json

# Specify region
python dump-enis.py --vpc-id vpc-12345678 --region us-west-2
```

### Advanced Usage

```bash
# Pipe to jq for processing
python dump-enis.py --vpc-id vpc-12345678 | jq '.NetworkInterfaces[].NetworkInterfaceId'

# Filter and save
python dump-enis.py --vpc-id vpc-12345678 | jq '.NetworkInterfaces[] | select(.Status == "in-use")' > active-enis.json

# Count ENIs by status
python dump-enis.py --vpc-id vpc-12345678 | jq '.NetworkInterfaces | group_by(.Status) | map({status: .[0].Status, count: length})'
```

### Command Line Options

- `--vpc-id` (required): VPC ID to dump ENIs from
- `--region`: AWS region (default: from AWS config)

## Output Format

The script generates a JSON file with the exact same structure as the EC2 `describe_network_interfaces()` API response:

```json
{
  "NetworkInterfaces": [
    {
      "NetworkInterfaceId": "eni-12345678",
      "SubnetId": "subnet-12345678",
      "VpcId": "vpc-12345678",
      "AvailabilityZone": "us-west-2a",
      "Description": "Primary network interface",
      "OwnerId": "123456789012",
      "RequesterId": "amazon-elb",
      "RequesterManaged": false,
      "Status": "in-use",
      "MacAddress": "02:12:34:56:78:90",
      "PrivateIpAddress": "10.0.1.100",
      "PrivateDnsName": "ip-10-0-1-100.us-west-2.compute.internal",
      "SourceDestCheck": true,
      "Groups": [
        {
          "GroupName": "default",
          "GroupId": "sg-12345678"
        }
      ],
      "Attachment": {
        "AttachmentId": "eni-attach-12345678",
        "DeviceIndex": 0,
        "InstanceId": "i-12345678",
        "InstanceOwnerId": "123456789012",
        "Status": "attached",
        "AttachTime": "2024-01-15T10:30:00.000Z",
        "DeleteOnTermination": true
      },
      "Association": {
        "PublicIp": "54.123.45.67",
        "PublicDnsName": "ec2-54-123-45-67.us-west-2.compute.amazonaws.com",
        "IpOwnerId": "123456789012"
      },
      "PrivateIpAddresses": [
        {
          "PrivateIpAddress": "10.0.1.100",
          "PrivateDnsName": "ip-10-0-1-100.us-west-2.compute.internal",
          "Primary": true,
          "Association": {
            "PublicIp": "54.123.45.67",
            "PublicDnsName": "ec2-54-123-45-67.us-west-2.compute.amazonaws.com",
            "IpOwnerId": "123456789012"
          }
        }
      ],
      "TagSet": [
        {
          "Key": "Name",
          "Value": "my-eni"
        },
        {
          "Key": "cluster.k8s.amazonaws.com/name",
          "Value": "my-eks-cluster"
        }
      ],
      "InterfaceType": "interface"
    }
  ]
}
```

## Requirements

- Python 3.6+
- boto3
- AWS credentials configured (via AWS CLI, environment variables, or IAM roles)

## Permissions Required

The script requires the following AWS permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets"
      ],
      "Resource": "*"
    }
  ]
}
```

## Use Cases

- **Network Inventory**: Get a complete inventory of all network interfaces in a VPC
- **Troubleshooting**: Analyze network configuration and identify issues
- **EKS Analysis**: Identify ENIs associated with EKS clusters and nodes
- **Security Audit**: Review security group assignments and network access
- **Cost Analysis**: Understand ENI usage patterns and optimize costs

## Example Output

```bash
$ python dump-enis.py --vpc-id vpc-12345678
Fetching ENIs for VPC: vpc-12345678
Found 25 ENIs
{
  "NetworkInterfaces": [
    {
      "NetworkInterfaceId": "eni-12345678",
      "SubnetId": "subnet-12345678",
      "VpcId": "vpc-12345678",
      "AvailabilityZone": "us-west-2a",
      "Description": "Primary network interface",
      "Status": "in-use",
      "MacAddress": "02:12:34:56:78:90",
      "PrivateIpAddress": "10.0.1.100",
      "Groups": [
        {
          "GroupName": "default",
          "GroupId": "sg-12345678"
        }
      ],
      "TagSet": [
        {
          "Key": "Name",
          "Value": "my-eni"
        }
      ]
    }
  ]
}
```

The output is pretty-formatted by default. Status messages go to stderr, JSON data goes to stdout, perfect for Unix-style piping and redirection.