
#!/usr/bin/env python3
"""
Dump all ENIs (Elastic Network Interfaces) under a specific VPC to JSON format.
Output matches the raw format from EC2's describe_network_interfaces() API.
"""

import argparse
import boto3
import json
import sys
from typing import List, Dict, Any


def list_network_interfaces_by_vpc(ec2_client: boto3.client, vpc_id: str) -> List[Dict[str, Any]]:
    """List all network interfaces in a specific VPC using direct VPC filter."""
    network_interfaces = []
    next_token = None

    while True:
        params = {
            "MaxResults": 1000,
            "Filters": [
                {
                    'Name': 'vpc-id',
                    'Values': [vpc_id]
                }
            ]
        }

        if next_token:
            params["NextToken"] = next_token

        try:
            response = ec2_client.describe_network_interfaces(**params)
            network_interfaces.extend(response["NetworkInterfaces"])

            if "NextToken" in response:
                next_token = response["NextToken"]
            else:
                break
        except Exception as e:
            print(f"Error describing network interfaces: {e}", file=sys.stderr)
            break

    return network_interfaces


def main():
    parser = argparse.ArgumentParser(
        description="Dump all ENIs under a specific VPC to JSON format (raw EC2 API format)"
    )
    parser.add_argument(
        "--vpc-id",
        required=True,
        help="VPC ID to dump ENIs from"
    )
    parser.add_argument(
        "--region",
        help="AWS region (default: from AWS config)"
    )
    
    args = parser.parse_args()
    
    # Initialize EC2 client
    session_kwargs = {}
    if args.region:
        session_kwargs['region_name'] = args.region
    
    try:
        ec2_client = boto3.client('ec2', **session_kwargs)
    except Exception as e:
        print(f"Error creating EC2 client: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Fetching ENIs for VPC: {args.vpc_id}", file=sys.stderr)
    
    # Get all ENIs in the VPC
    enis = list_network_interfaces_by_vpc(ec2_client, args.vpc_id)
    
    if not enis:
        print(f"No ENIs found in VPC {args.vpc_id}", file=sys.stderr)
        sys.exit(0)
    
    print(f"Found {len(enis)} ENIs", file=sys.stderr)
    
    # Output raw ENI data in the same format as describe_network_interfaces
    output_data = {
        "NetworkInterfaces": enis
    }
    
    # Output pretty-formatted JSON to stdout
    try:
        json.dump(output_data, sys.stdout, indent=2, default=str)
        print()  # Add newline at end
    except Exception as e:
        print(f"Error writing to stdout: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
