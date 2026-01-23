
#### How to use

1. Decide sender email address, and receiver email address.
1. Create the email identities for the email addresses (both for sender and receiver) on the SES management console.
1. Verify the email addresses.
1. Deploy the CloudFormation template. Specify the email addresses as the parameters.
1. Confirm that you can receive notification emails by changing the cluster status (e.g., scaling up/down).
    - For HyperPod EKS, you can test the node health notification by triggering instance replacement.
    - For HyperPod Slurm, as of 2025-05, you cannot test the node health notification. It comes when the node really got degraded at EC2 level.


#### Utility: Dump cluster events

Use the `dump_cluster_events.py` script to analyze event variations and decide how to implement email formatting:

```bash
# Dump all events for a cluster
make dump-events CLUSTER_NAME=my-cluster

# Specify region and output file
make dump-events CLUSTER_NAME=my-cluster REGION=us-east-1 OUTPUT=events.json

# Or use the script directly
python3 dump_cluster_events.py --cluster-name my-cluster --region us-west-2 --pretty
```

This helps you see the actual EventDetails structure from your cluster to implement appropriate email formatting.
