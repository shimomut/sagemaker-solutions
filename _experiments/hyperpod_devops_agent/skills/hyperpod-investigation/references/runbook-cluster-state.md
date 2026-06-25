# Runbook: SageMaker HyperPod Cluster State Change

Triggered by EventBridge events with detail-type
`SageMaker HyperPod Cluster State Change`. The payload includes
`detail.ClusterStatus` and `detail.InstanceGroups[]` with per-group counts.

## Status meanings

| `ClusterStatus` | What it means | Severity |
| --- | --- | --- |
| `Creating` | Cluster is being created. | Informational |
| `InService` | Cluster is healthy and ready. | Informational |
| `Updating` | An update (instance group resize, software update) is in flight. | Routine |
| `Deleting` | Cluster is being deleted. | Routine |
| `Failed` | Cluster is in a failure state and not serving workloads. | **Critical** |
| `RollingBack` | An update failed and is being reversed. | **Critical** |
| `SystemUpdating` | Service-initiated maintenance. | Informational |

## Step 1: Confirm the live status

Call `sagemaker:DescribeCluster`. Compare the live `ClusterStatus` with the
event payload. If they no longer match, the cluster transitioned again after
the event was emitted; that latest state is what matters.

## Step 2: Inspect instance group reconciliation

For each group in `detail.InstanceGroups[]`:

- `Status` — `Creating`, `InService`, `Updating`, `Failed`, `Deleting`.
- `CurrentCount` vs `TargetCount` — drift indicates ongoing scaling or
  replacement.

Failed groups warrant per-group investigation:

1. `sagemaker:ListClusterNodes --instance-group-name <group>` to enumerate
   the EC2 instances in that group.
2. For each instance: `ec2:DescribeInstanceStatus`.
3. `sagemaker:ListClusterEvents --cluster-name <name>` for context within the
   last hour.

## Step 3: Reason about the transition

| Transition | Likely cause |
| --- | --- |
| `InService` → `Updating` | Operator-initiated scale or update; cross-check with CloudTrail `UpdateCluster` events. |
| `Updating` → `Failed` | Capacity unavailable for requested instance type, lifecycle script failed, or VPC misconfiguration. |
| `Updating` → `RollingBack` | An update partially applied and is being reverted; one or more groups likely failed health checks. |
| `InService` → `Failed` | Catastrophic event — typically widespread node-health issues; correlate with recent Node Health Events. |

## Step 4: Output

Provide:

- Live `ClusterStatus` and the transition timeline.
- Per-group health summary (Target vs Current vs Status).
- For each failed group: which instances failed and the underlying EC2/EKS
  reasons.
- Whether the cluster has `NodeRecovery=Automatic` and what the service is
  doing about the failure already.
