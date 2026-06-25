"""Send a synthetic HyperPod event to the DevOps Agent webhook from your laptop.

Useful for end-to-end smoke testing without waiting for a real cluster event.
The script reads the webhook URL/secret from the same Secrets Manager entry
the Lambda uses (default name: hyperpod-devops-agent/webhook).

Example:
    python3 local_test.py --event-type cluster-state-change
"""
import argparse
import json
import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).parent))
import lambda_function


SAMPLE_EVENTS = {
    "cluster-state-change": {
        "version": "0",
        "id": "00000000-0000-0000-0000-000000000001",
        "detail-type": "SageMaker HyperPod Cluster State Change",
        "source": "aws.sagemaker",
        "account": "842413447717",
        "time": "2026-06-25T20:00:00Z",
        "region": "us-west-2",
        "detail": {
            "ClusterArn": "arn:aws:sagemaker:us-west-2:842413447717:cluster/lw12e0dn1hhd",
            "ClusterName": "k8-1",
            "ClusterStatus": "Failed",
            "InstanceGroups": [
                {
                    "InstanceGroupName": "worker1",
                    "Status": "Failed",
                    "CurrentCount": 0,
                    "TargetCount": 1,
                },
            ],
        },
    },
    "node-health": {
        "version": "0",
        "id": "00000000-0000-0000-0000-000000000002",
        "detail-type": "SageMaker HyperPod Cluster Node Health Event",
        "source": "aws.sagemaker",
        "account": "842413447717",
        "time": "2026-06-25T20:00:00Z",
        "region": "us-west-2",
        "detail": {
            "ClusterArn": "arn:aws:sagemaker:us-west-2:842413447717:cluster/lw12e0dn1hhd",
            "ClusterName": "k8-1",
            "InstanceId": "i-0123456789abcdef0",
            "HealthSummary": {
                "HealthStatus": "Unhealthy",
                "HealthStatusReason": "GPU_DCGM_HEALTH_CHECK_FAILED",
                "RepairAction": "Replace",
                "Recommendation": "Replace the node to restore capacity.",
            },
        },
    },
    "cluster-event": {
        "version": "0",
        "id": "00000000-0000-0000-0000-000000000003",
        "detail-type": "SageMaker HyperPod Cluster Event",
        "source": "aws.sagemaker",
        "account": "842413447717",
        "time": "2026-06-25T20:00:00Z",
        "region": "us-west-2",
        "detail": {
            "ClusterArn": "arn:aws:sagemaker:us-west-2:842413447717:cluster/lw12e0dn1hhd",
            "EventDetails": {
                "ClusterName": "k8-1",
                "ResourceType": "Node",
                "InstanceGroupName": "worker1",
                "InstanceId": "i-0123456789abcdef0",
                "EventTime": "1750000000000",
                "Description": "Node entered NotReady state for over 5 minutes.",
            },
        },
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event-type",
        choices=sorted(SAMPLE_EVENTS),
        default="node-health",
    )
    parser.add_argument(
        "--secret-name",
        default=os.environ.get("WEBHOOK_SECRET_NAME", "hyperpod-devops-agent/webhook"),
    )
    parser.add_argument("--region", default=os.environ.get("REGION", "us-west-2"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the constructed DevOps Agent payload without sending it.",
    )
    args = parser.parse_args()

    event = SAMPLE_EVENTS[args.event_type]

    if args.dry_run:
        payload = lambda_function._build_payload(event)
        print(json.dumps(payload, indent=2))
        return

    sm = boto3.client("secretsmanager", region_name=args.region)
    secret = json.loads(sm.get_secret_value(SecretId=args.secret_name)["SecretString"])
    print(f"Sending {args.event_type!r} payload to {secret['url']}")
    payload = lambda_function._build_payload(event)
    print(json.dumps(payload, indent=2))
    lambda_function._post(secret["url"], secret["secret"], payload)
    print("Webhook accepted.")


if __name__ == "__main__":
    main()
