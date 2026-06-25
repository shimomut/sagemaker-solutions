# HyperPod resource map

A SageMaker HyperPod cluster is a composition of AWS resources across multiple
services. This page enumerates every component and the API to reach it, so an
investigation can pivot from "an event about cluster X" to live state across
the stack.

## Top-down view

```
HyperPod cluster (SageMaker)
├─ Orchestrator
│   └─ EKS cluster   (EKS-orchestrated HyperPod only)
│       ├─ Managed nodegroups / Karpenter-provisioned nodes
│       ├─ Pods (DaemonSets: nvidia-device-plugin, efa-device-plugin, FSx CSI, ...)
│       └─ EKS access entries (this is how the agent reads the cluster)
├─ Instance groups
│   └─ EC2 instances (ml.<family>.<size>)
│       ├─ Local NVMe (InstanceStorageConfig.EbsVolumeConfig)
│       ├─ EFA network interfaces (for GPU instance types)
│       └─ IAM execution role (per instance group)
├─ Networking
│   ├─ VPC + subnets (cluster-level VpcConfig and per-group OverrideVpcConfig)
│   └─ Security groups
├─ Storage
│   ├─ FSx Lustre (mounted via the FSx CSI driver)
│   └─ S3 (lifecycle scripts, optional checkpointing)
├─ Lifecycle scripts (S3 path on each InstanceGroup.LifeCycleConfig)
└─ Recovery policy
    ├─ NodeRecovery: Automatic | None
    └─ AutoScaling: Karpenter (EKS) | none
```

## Naming patterns

- **HyperPod cluster name** is user-chosen (e.g. `k8-1`).
- **HyperPod cluster ARN** is `arn:aws:sagemaker:<region>:<account>:cluster/<8-12 char id>`.
- **Underlying EKS cluster name** typically follows `sagemaker-<hyperpod-name>-<8-hex>-eks`.
  Confirm by reading `Orchestrator.Eks.ClusterArn` — never assume from the name alone.
- **HyperPod node name** in Kubernetes is `hyperpod-i-<ec2-instance-id>` (e.g.
  `hyperpod-i-0da6589e2bbb9b628`). The bare EC2 instance ID also appears in
  `ListClusterNodes` output and EventBridge events.

## API map

| Question | Service | API |
| --- | --- | --- |
| Is the cluster healthy? | SageMaker | `DescribeCluster` |
| Which instance groups exist and at what counts? | SageMaker | `DescribeCluster` → `InstanceGroups[]` |
| Which nodes exist, what is each one's status? | SageMaker | `ListClusterNodes` |
| What recent events fired on this cluster? | SageMaker | `ListClusterEvents` |
| Is a specific EC2 instance healthy? | EC2 | `DescribeInstanceStatus`, `DescribeInstances` |
| Is a specific Kubernetes node healthy? | EKS (kubectl) | `kubectl describe node hyperpod-i-<id>` |
| Are pods on a node CrashLoopBackOff / Pending? | EKS (kubectl) | `kubectl get pods --field-selector spec.nodeName=...` |
| Are there cluster-wide K8s events? | EKS (kubectl) | `kubectl get events -A --sort-by=.lastTimestamp` |
| Is FSx Lustre healthy? | FSx | `DescribeFileSystems` for any FSx referenced by the VPC |
| Is Karpenter scaling correctly? | EKS (kubectl) | `kubectl get nodepools.karpenter.sh, nodeclaims` |

## Common control-plane events (`aws.sagemaker`)

| Detail-type | When it fires |
| --- | --- |
| SageMaker HyperPod Cluster State Change | Cluster transitions between `Creating`, `InService`, `Updating`, `Failed`, `Deleting`, `RollingBack`. |
| SageMaker HyperPod Cluster Node Health Event | Per-node degradation detected by the HyperPod health system (EFA, GPU/DCGM, kubelet, instance-status). Carries `HealthSummary` with `HealthStatus`, `HealthStatusReason`, `RepairAction`, `Recommendation`. |
| SageMaker HyperPod Cluster Event | Generic catch-all. `EventDetails.ResourceType` says what kind of thing the event is about (Cluster / InstanceGroup / Node). Carries a `Description` string. |
