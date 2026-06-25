---
name: hyperpod-investigation
description: |
  Use this skill when investigating SageMaker HyperPod clusters. Triggers include:
  incident titles or descriptions that mention "HyperPod", "SageMaker cluster",
  "ClusterName", or an ARN of the form arn:aws:sagemaker:*:*:cluster/*; events
  with source aws.sagemaker and detail-type "SageMaker HyperPod Cluster State Change",
  "SageMaker HyperPod Cluster Node Health Event", or "SageMaker HyperPod Cluster Event";
  and incidents that mention node health degradation, EFA / NCCL failures, FSx
  Lustre throughput drops, or NotReady nodes on an EKS cluster whose name matches
  sagemaker-*-eks. This skill explains how a HyperPod cluster maps onto its
  underlying EKS cluster, instance groups, EC2 instances, FSx file systems, and
  VPC, and gives investigation procedures for the three EventBridge detail-types
  above.
---

# HyperPod Investigation

Use this skill whenever an incident points at a SageMaker HyperPod cluster. A
HyperPod cluster is **not** a single AWS resource — it is a composition. Before
applying any per-event procedure below, build the resource map for the cluster
named in the incident (see `references/hyperpod-resource-map.md`).

## Step 1: Identify the cluster

The cluster name is in one of these payload fields, in order of preference:

1. `data.metadata.clusterName` (set by the webhook bridge).
2. `data.originalEvent.detail.ClusterName`.
3. `data.originalEvent.detail.EventDetails.ClusterName`.
4. Any ARN of the form `arn:aws:sagemaker:<region>:<account>:cluster/<id>` in
   the description — call `sagemaker:DescribeCluster` with the ARN.

Once you have the cluster name, capture the region and account from
`data.metadata.region` and `data.metadata.account`.

## Step 2: Build the resource map

Resolve the cluster's component resources before drawing any conclusions:

| What | How |
| --- | --- |
| Orchestrator (EKS or Slurm) | `sagemaker:DescribeCluster` → `Orchestrator.Eks.ClusterArn` (EKS) or absent (Slurm). |
| EKS cluster name | The last segment of the EKS ARN. Typical pattern: `sagemaker-<hyperpod-name>-<8-hex>-eks`. |
| Instance groups | `sagemaker:DescribeCluster` → `InstanceGroups[]`. Each has `InstanceGroupName`, `InstanceType`, `CurrentCount`, `TargetCount`, `Status`. |
| Individual nodes | `sagemaker:ListClusterNodes` → returns instance IDs `i-...` and their HyperPod node names `hyperpod-i-...`. |
| Underlying EC2 instances | The `i-...` returned above. Look them up directly in EC2 if needed. |
| FSx Lustre file systems | Inspect the EKS PVs (StorageClassName starting with `fsx-`) or the VPC's FSx resources. |
| VPC + subnets + security groups | `sagemaker:DescribeCluster` → `VpcConfig` (cluster-level) and `InstanceGroups[].OverrideVpcConfig`. |
| Auto-scaling | `sagemaker:DescribeCluster` → `AutoScaling` (Karpenter is common for EKS HyperPod). |
| Node recovery policy | `sagemaker:DescribeCluster` → `NodeRecovery` (typically `Automatic`). |

For more, see `references/hyperpod-resource-map.md`.

## Step 3: Apply the per-event procedure

| EventBridge detail-type | Procedure |
| --- | --- |
| SageMaker HyperPod Cluster Node Health Event | `references/runbook-node-health.md` |
| SageMaker HyperPod Cluster State Change | `references/runbook-cluster-state.md` |
| SageMaker HyperPod Cluster Event | `references/runbook-cluster-event.md` |

If the incident description does not reference a HyperPod EventBridge event,
fall back to Step 2's resource map + the EKS access entry to inspect live
cluster state.

## Step 4: Cross-check synthetic vs. real

If the reported instance ID does not appear in `sagemaker:ListClusterNodes`
output for the cluster, **say so explicitly**. Possible causes:
- The event refers to an instance that has already been replaced.
- The event is a synthetic / test payload (incident IDs like
  `hyperpod-00000000-0000-0000-0000-...` are produced by this repo's
  smoke-test tooling, not real HyperPod events).
- The cluster name in the event no longer matches the live cluster.

Reconciling the synthetic payload against the real cluster state is part of the
root cause analysis — do not silently substitute a different instance.

## Step 5: Output

Report:

1. **Cluster identification** — name, region, account, orchestrator type, total
   nodes (target vs. current per instance group).
2. **Incident reconciliation** — does the incident map onto real cluster state?
   If not, why?
3. **Root cause hypothesis** — anchored to the relevant per-event procedure.
4. **Recommended action** — quote `HealthSummary.RepairAction` /
   `HealthSummary.Recommendation` verbatim when present. HyperPod's
   `NodeRecovery=Automatic` means the service is already attempting recovery
   for many node-health events; surface that fact instead of recommending the
   user do something the service is already doing.

## Out of scope

- Modifying cluster state. The agent has read-only EKS access and no write
  access to SageMaker. Mitigation is always a *recommendation* to the operator.
- Slurm-orchestrated HyperPod clusters. The on-cluster signals live on the
  head node and are reachable only via SSM. This skill covers what the agent
  can do without SSM; SSM-based diagnostics are a separate concern.
