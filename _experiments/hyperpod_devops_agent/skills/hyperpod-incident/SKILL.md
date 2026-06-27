---
name: hyperpod-incident
description: Triage and investigate a SageMaker HyperPod incident in a single pass. Loaded when an investigation is triggered by a HyperPod EventBridge event (cluster state change, node health, cluster event). Decides whether HyperPod's built-in resiliency is recovering the situation (suppress / monitor) or whether the operator must intervene (escalate), then produces a human-readable explanation with recommended actions. Replaces the upstream `hyperpod-*` skills' on-node procedures with proxy-signal investigation that works inside the DevOps Agent permission guardrail.
metadata:
  version: "0.1.0"
  agent_types: ["INCIDENT_TRIAGE", "INCIDENT_RCA"]
---

# HyperPod incident skill

This skill is the **single entry point** for any investigation triggered
by a HyperPod EventBridge event. It does triage and root-cause analysis
in one pass because they need the same evidence: snapshot data
(`describe-cluster`, `describe-cluster-node`) alone cannot distinguish
"HyperPod is auto-recovering" from "HyperPod has given up" — only the
cross-source timeline can.

**Operating policy.** Read-only. Never call a state-changing API.
Present every action that mutates anything (operator-driven replacement,
SSM session, label change) as a **Recommended action (operator runs
this)** block. The customer's operator decides whether to execute it.

**Required reading.** Open
[references/hyperpod-mental-model.md](references/hyperpod-mental-model.md)
in parallel with this skill. The mental-model doc is the ground truth
for what each HyperPod signal means; this skill is the decision
procedure that consumes those meanings.

## Why one skill, not two

A single failed instance can vanish from `list-cluster-nodes` between
retry attempts, and HyperPod may auto-retry from `Failed` status —
neither is a terminal escalation signal on its own. Distinguishing
"still retrying within budget" from "stuck" requires the full
`list-cluster-events` chain, the HMA CloudWatch stream, and the cluster
status all aligned on a wall-clock timeline. Building a separate
"triage" skill that decides without that data would mean re-deciding
incorrectly on every event.

## Workflow

### Phase 1 — Gather (run in parallel)

For the incident referenced in the trigger event (cluster name + optional
instance id), collect these in parallel. **Do not stop on a single
signal — gather all of them before classifying.**

1. **Cluster state**: `aws sagemaker describe-cluster --cluster-name <name>`
   — current `ClusterStatus`, `NodeRecovery`, `Orchestrator` (Eks vs.
   Slurm), `InstanceGroups[].CurrentCount` / `TargetCount` / `Status`.
2. **Node inventory**: `aws sagemaker list-cluster-nodes --cluster-name <name>`
   plus `describe-cluster-node` for any instance id named in the trigger
   event. **An instance id mentioned in the event that is NOT in
   `list-cluster-nodes` is a signal, not an error** — the node may have
   been removed mid-retry.
3. **Cluster events chain**: `aws sagemaker list-cluster-events --cluster-name <name>`,
   paginated to ≥200 entries or until events reach 24 hours back,
   whichever comes first. This is the **canonical record of replacement
   attempts including failed ones** and survives nodes disappearing
   from the node list.
   - Available on EKS clusters and on Slurm clusters with **Continuous
     Provisioning** enabled. If the API returns
     `ValidationException`/equivalent on a Slurm cluster without CP,
     note "event timeline unavailable; confidence degraded" in the
     final report and proceed with the remaining sources.
4. **HMA CloudWatch stream**: log group
   `/aws/sagemaker/Clusters/<NAME>/<CLUSTER_ID>`, streams matching
   `SagemakerHealthMonitoringAgent/*` (filter to the affected instance
   group / instance if known). Filter for `HealthMonitoringAgentDetectionEvent`
   entries and any Xid / DCGM / EFA / OOM messages within the same
   window as Phase 1 step 3.
5. **Lifecycle script stream** (only if a replace attempt is in the
   timeline): same log group, streams matching `LifecycleConfig/*` for
   the affected instance group / instance id. Look for non-zero exit,
   timeout, S3 / IAM errors.
6. **EKS node state** (EKS only): `kubectl get node <name> -o yaml` for
   the affected node (if still present). Surface
   `sagemaker.amazonaws.com/node-health-status`, `fault-types`,
   `fault-reasons`, `fault-details` labels/annotations and any taints.
7. **Slurm node state** (Slurm only, if SSM not required): use what's
   reachable from the control plane — `describe-cluster-node` gives
   most of what we need; deep `scontrol`/`sinfo` requires SSM and is
   out of scope here.

### Phase 2 — Reconstruct the timeline

Build a single ordered timeline keyed by UTC timestamp across all
sources, restricted to the affected scope (cluster, instance group, or
instance). Mark each entry with its source. The shape should be:

```
T+0:00   [HMA]            HealthMonitoringAgentDetectionEvent — Xid 79 on GPU 3
T+0:32   [ClusterEvent]   Action:Replace marked on i-aaa (NodeRecovery=Automatic)
T+0:33   [Node]           list-cluster-nodes: i-aaa removed
T+0:34   [ClusterEvent]   Replacement started for instance group worker1
T+18:21  [ClusterEvent]   Replacement failed: EFA health checks did not run successfully
T+18:25  [Node]           list-cluster-nodes: still missing
T+20:10  [ClusterEvent]   Replacement started for instance group worker1   ← second attempt
...
```

This is the artifact the classification phase reasons over. Include it
in the final report regardless of verdict — operators need it to
double-check the agent's call.

### Phase 3 — Classify

Apply the rules below **in order**. Stop at the first match.

| # | Signal pattern | Verdict |
|---|---|---|
| 1 | Trigger detail-type is `Cluster Event` with `EventLevel=Info` and the timeline shows no node-health activity | **Suppress** |
| 2 | Cluster status is `Failed` or `RollingBack` | **Escalate** (cluster-level) |
| 3 | `NodeRecovery=None` on the cluster AND a node has been marked `Action:*` / `UnschedulablePending*` AND no replacement has started within 5 minutes | **Escalate** — auto-recovery is off; operator must trigger replacement |
| 4 | Exactly one replacement attempt in flight, started within the last 30 minutes, no prior failure in the chain | **Monitor — first attempt** (next re-check in 30 min) |
| 5 | Multiple replacement attempts in the chain, total elapsed since the first failure ≤ 90 minutes, the most recent attempt is *Running* or *Started* (not yet failed) | **Monitor — elevated** (retry in progress, watch closely) |
| 6 | Multiple replacement attempts, total elapsed > 90 minutes, no successful `Running` transition, AND no new attempt started within the last 30 minutes | **Escalate** — retry chain is stuck |
| 7 | Node was in `Failed` state AND no new replacement attempt has started within the last 30 minutes AND total time in failing chain > 60 minutes | **Escalate** — HyperPod has given up |
| 8 | Instance id from the trigger event is missing from `list-cluster-nodes` AND `list-cluster-events` shows no new attempt for the last 30 minutes AND the most recent attempt failed | **Escalate** — instance vanished, no retry |
| 9 | HMA detection event present but no corresponding `Action:*` / replacement event in the timeline within 10 minutes | **Escalate** — HMA fired without escalating; investigate why (mismatch in node-recovery config, signal didn't classify) |
| 10 | None of the above match | **Monitor — uncategorized** (include the full timeline; flag for review) |

**Time budgets are not hardcoded constants — they encode the
mental-model doc's "How long things take" section.** A single replace
takes 20–30 min; two attempts plus a slack gap = ~90 min. Don't change
these without updating the mental-model doc first.

### Phase 4 — Report

Every report — whether `Suppress`, `Monitor`, or `Escalate` — produces
the same structure:

```
## Verdict

<Suppress | Monitor (first attempt | elevated | uncategorized) | Escalate>

## What HyperPod is doing right now

<one paragraph in plain English; reference the timeline>

## Timeline

<the timeline from Phase 2>

## Evidence sources consulted

<list each Phase 1 source with whether it returned data and any caveats
(e.g. "list-cluster-events unavailable on this Slurm cluster — Continuous
Provisioning not enabled; confidence degraded")>

## Confidence

<direct observation | proxy inference | unverifiable> for each material
claim in the verdict explanation.

## Recommended actions (operator runs these)

<empty if Suppress or Monitor; otherwise a numbered list of the
specific operator commands that close the gap>

## Next re-check

<only for Monitor verdicts: UTC timestamp when this should be revisited>
```

For `Monitor` verdicts, the report explicitly tells the human "no
action needed; HyperPod is recovering; expect completion by HH:MM UTC.
You will be notified again only if the situation changes." This is the
key UX improvement — silence is bad; "we're watching and here's why
we're not alarming you" is good.

## Inputs the skill expects from the trigger

The webhook payload built by the bridge Lambda passes these fields in
the investigation context:

- `data.metadata.clusterName` — HyperPod cluster name (required)
- `data.metadata.detailType` — `Cluster State Change` /
  `Cluster Node Health Event` / `Cluster Event`
- `data.originalEvent.detail.InstanceId` — affected instance (for node
  health events)
- `data.originalEvent.detail.EventDetails.InstanceGroupName` /
  `InstanceId` (for cluster events)

If the cluster name is missing, abort with "skill cannot run without a
HyperPod cluster name — check the webhook bridge's payload mapping."

## What this skill does NOT do

- **It does not SSH or run SSM on nodes.** The DevOps Agent permission
  guardrail blocks `ssm:StartSession` / `ssm:SendCommand`. When on-node
  evidence is needed (Xid in `dmesg`, DCGM counters, kubelet journal),
  the skill emits a recommendation that includes the exact SSM command
  for the operator to run, never executes it.
- **It does not replace nodes.** `batch-replace-cluster-nodes` is a
  state-changing call; the skill recommends it but never invokes it.
- **It does not modify Slurm or EKS state.** No `scontrol update`, no
  `kubectl cordon`, no label edits.

## Tools used (in-guardrail)

- `sagemaker:DescribeCluster`, `ListClusterNodes`, `DescribeClusterNode`,
  `ListClusterEvents`
- `logs:FilterLogEvents`, `logs:DescribeLogStreams` on
  `/aws/sagemaker/Clusters/*`
- `eks:DescribeCluster` (read-only) and `kubectl get/describe`
  (via the access entry created by `make eks-access`)
- `cloudwatch:GetMetricData` on `ClusterAgent` and
  `SagemakerHealthMonitoringAgent` namespaces — useful for time-series
  confirmation when individual log events are sparse
