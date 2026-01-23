#!/usr/bin/env python3
"""
Utility script to dump all HyperPod cluster events.
Use this to see variations of EventDetails and decide how to implement email formatting code.
"""
import json
import argparse
from datetime import datetime

import boto3


def list_cluster_events_all(sagemaker_client, cluster_name):
    """List all events for a given cluster with pagination."""
    events = []
    next_token = None
    
    while True:
        params = {"ClusterName": cluster_name}
        if next_token:
            params["NextToken"] = next_token
        
        response = sagemaker_client.list_cluster_events(**params)
        events += response["Events"]
        
        if "NextToken" in response and response["NextToken"]:
            next_token = response["NextToken"]
            continue
        break
    
    return events


def datetime_converter(obj):
    """Convert datetime objects to ISO format strings for JSON serialization."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def main():
    parser = argparse.ArgumentParser(
        description="Dump all HyperPod cluster events to analyze EventDetails variations"
    )
    parser.add_argument(
        "--cluster-name",
        required=True,
        help="Name of the HyperPod cluster"
    )
    parser.add_argument(
        "--region",
        default="us-west-2",
        help="AWS region (default: us-west-2)"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path (default: stdout)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print JSON output"
    )
    
    args = parser.parse_args()
    
    # Create SageMaker client
    sagemaker_client = boto3.client("sagemaker", region_name=args.region)
    
    # Fetch all events
    print(f"Fetching events for cluster: {args.cluster_name}...", flush=True)
    events = list_cluster_events_all(sagemaker_client, args.cluster_name)
    print(f"Found {len(events)} events", flush=True)
    
    # Prepare output
    indent = 2 if args.pretty else None
    output_data = {
        "ClusterName": args.cluster_name,
        "Region": args.region,
        "TotalEvents": len(events),
        "Events": events
    }
    
    json_output = json.dumps(output_data, indent=indent, default=datetime_converter)
    
    # Write output
    if args.output:
        with open(args.output, "w") as f:
            f.write(json_output)
        print(f"Events written to: {args.output}")
    else:
        print("\n" + json_output)


if __name__ == "__main__":
    main()
