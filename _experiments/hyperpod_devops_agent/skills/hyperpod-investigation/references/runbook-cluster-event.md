# Runbook: SageMaker HyperPod Cluster Event

Triggered by EventBridge events with detail-type
`SageMaker HyperPod Cluster Event`. This is the generic catch-all for events
that don't fit the dedicated State Change or Node Health detail-types.

The shape:

```
detail.EventDetails = {
  ClusterName: string,
  ResourceType: "Cluster" | "InstanceGroup" | "Node",
  InstanceGroupName?: string,
  InstanceId?: string,
  EventTime: <epoch millis as string>,
  Description: string
}
```

## Step 1: Switch on ResourceType

| `ResourceType` | Procedure |
| --- | --- |
| `Cluster` | Treat like a cluster-wide notice. Cross-check with `sagemaker:DescribeCluster` and recent `ListClusterEvents`. |
| `InstanceGroup` | Look at the named group only. Compare `CurrentCount` / `TargetCount` / `Status` from `DescribeCluster`. |
| `Node` | Look at the named instance: `ec2:DescribeInstanceStatus` and `kubectl describe node hyperpod-i-<id>`. Cross-reference with recent Node Health Events for the same instance. |

## Step 2: Parse the Description

The `Description` is free-text but typically follows a pattern such as:

- `"Node entered NotReady state for over 5 minutes."` — investigate kubelet and
  the K8s node conditions.
- `"Instance group worker1 scaled from 4 to 6 instances."` — routine; only
  worth investigating if the new instances didn't reach InService.
- `"Lifecycle script <name> failed on instance i-..."` — fetch the lifecycle
  script's S3 path from `InstanceGroup.LifeCycleConfig` and consult logs.

When the description is ambiguous, call `sagemaker:ListClusterEvents` with the
matching event time window for additional context.

## Step 3: Output

Report:

- What resource the event references.
- Live state of that resource (per Step 1).
- Whether the event is a routine notice or warrants action.
