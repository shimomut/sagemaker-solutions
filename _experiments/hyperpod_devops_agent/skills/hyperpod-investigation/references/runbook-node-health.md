# Runbook: SageMaker HyperPod Cluster Node Health Event

Triggered by EventBridge events with detail-type
`SageMaker HyperPod Cluster Node Health Event`. The payload includes
`detail.InstanceId` and `detail.HealthSummary.{HealthStatus, HealthStatusReason,
RepairAction, Recommendation}`.

## Step 1: Confirm the instance exists on the cluster

Call `sagemaker:ListClusterNodes` for the cluster name. Look for an entry whose
`InstanceId` matches the event. If absent:

- The node may have already been replaced (NodeRecovery=Automatic).
- The event may be synthetic (see SKILL.md Step 4).

Report the discrepancy explicitly and stop unless instructed to continue.

## Step 2: Inspect the EC2 instance

Call `ec2:DescribeInstanceStatus` for the instance ID. Look for:

- `InstanceStatus.Status != ok`
- `SystemStatus.Status != ok`
- Any pending `Events` (scheduled maintenance, retirement).

## Step 3: Inspect the Kubernetes node

The K8s node name is `hyperpod-i-<ec2-id>`. Via the EKS access entry:

- `kubectl describe node hyperpod-i-<id>` — look at `Conditions` (Ready,
  MemoryPressure, DiskPressure, PIDPressure), `Taints`, and `Events`.
- `kubectl get pods --all-namespaces --field-selector spec.nodeName=hyperpod-i-<id>`
  — note CrashLoopBackOff, Evicted, ImagePullBackOff.
- `kubectl logs -n kube-system <daemonset-pod-on-node>` — especially for
  `nvidia-device-plugin`, `aws-efa-k8s-device-plugin`, `fsx-csi-node`.

## Step 4: Match the failure reason

Common `HealthStatusReason` values and where to look:

| Reason | Where to look |
| --- | --- |
| `GPU_DCGM_HEALTH_CHECK_FAILED` | EC2 instance + `nvidia-device-plugin` logs on the node. Likely an XID error in dmesg. |
| `EFA_HEALTH_CHECK_FAILED` | EC2 ENI/EFA status. Check `aws-efa-k8s-device-plugin` pod logs. |
| `EBS_VOLUME_HEALTH_CHECK_FAILED` | `ec2:DescribeVolumes` for the InstanceStorageConfig volume. |
| `INSTANCE_STATUS_CHECK_FAILED` | `ec2:DescribeInstanceStatus`. Often a hardware issue. |
| `KUBELET_UNHEALTHY` | `kubectl describe node` Conditions; node may be NotReady. |

## Step 5: Recommend action

`HealthSummary.RepairAction` is the action the HyperPod service plans to take:

- `Replace` — service will replace the node automatically when
  `NodeRecovery=Automatic`. Surface this and tell the operator to monitor;
  do not recommend they manually replace.
- `Reboot` — service will reboot the EC2 instance.
- `None` — service has no automated action; this is human-triage territory.

Quote `HealthSummary.Recommendation` verbatim. If it is missing, fall back to a
recommendation derived from the matched failure reason in Step 4.
