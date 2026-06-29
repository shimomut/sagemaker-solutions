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
   paginated to ≥500 entries or until events reach **7 days** back,
   whichever comes first. This is the **canonical record of replacement
   attempts including failed ones** and survives nodes disappearing
   from the node list. The wider 7-day window also feeds the recurring-
   pattern classification rules in Phase 3 — don't shorten the lookback
   even when the trigger event is recent.
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

### Phase 2b — Compute recurrence statistics

Over the 7-day `list-cluster-events` window from Phase 1, compute and
record (used by Phase 3 rules 4–6):

- `replacements_7d_total` — count of `Replace` actions / replacement-
  started cluster events across the whole cluster in the last 7 days.
- `replacements_7d_by_group[<ig>]` — same, partitioned by InstanceGroup.
- `replacements_24h_total` — same metric, 24h window.
- `xid_signature_count_7d[<xid_code>]` — count of distinct replacement
  attempts whose HMA detection event referenced the same Xid code in
  the last 7 days. The Xid code is extracted from the HMA detection
  event's description (e.g. `"Xid 74"` in the line `NVRM: Xid (PCI:...) :
  74, ...`). Include the affected InstanceGroup in the count
  partitioning so "Xid 74 on worker2 ×3" is distinguishable from
  "Xid 74 spread across worker2/worker3/worker4".

Include these counts in the verdict description's "What HyperPod is
doing right now" paragraph when they're ≥2 — even if the verdict
itself doesn't change, the operator should see the count.

### Phase 3 — Classify

Apply the rules below **in order**. Stop at the first match.

The recurring-pattern rules (4–6) are checked **before** the
single-incident rules (7–11) — a node that's auto-recovering for the
3rd time this week should be flagged as a pattern, not silently
classified as `Monitor — first attempt`.

| # | Signal pattern | Verdict |
|---|---|---|
| 1 | Trigger detail-type is `Cluster Event` with `EventLevel=Info` and the timeline shows no node-health activity | **Suppress** |
| 2 | Cluster status is `Failed` or `RollingBack` | **Escalate** (cluster-level) |
| 3 | `NodeRecovery=None` on the cluster AND a node has been marked `Action:*` / `UnschedulablePending*` AND no replacement has started within 5 minutes | **Escalate** — auto-recovery is off; operator must trigger replacement |
| 4 | `xid_signature_count_7d[(<xid>, <ig>)] ≥ 3` — same Xid code has caused ≥3 replacements on the same InstanceGroup in the last 7 days (auto-recovery may be succeeding each time) | **Escalate — recurring hardware fault pattern**: HyperPod is repairing the symptom, but a hardware vendor / capacity investigation is warranted. Include the timestamps of all prior occurrences. |
| 5 | `replacements_24h_total ≥ 5` — five or more replacements anywhere in the cluster within 24 hours | **Escalate — fleet-wide instability**: the rate of node churn is abnormal regardless of individual root causes. |
| 6 | `replacements_7d_by_group[<ig>] ≥ 5` — five or more replacements on the same InstanceGroup in 7 days | **Escalate — instance-group instability**: the affected IG (which may be a specific SKU or topology placement) is failing more often than the rest of the cluster. |
| 7 | Exactly one replacement attempt in flight, started within the last 30 minutes, no prior failure in the chain | **Monitor — first attempt** (next re-check in 30 min) |
| 8 | Multiple replacement attempts in the chain, total elapsed since the first failure ≤ 90 minutes, the most recent attempt is *Running* or *Started* (not yet failed) | **Monitor — elevated** (retry in progress, watch closely) |
| 9 | Multiple replacement attempts, total elapsed > 90 minutes, no successful `Running` transition, AND no new attempt started within the last 30 minutes | **Escalate** — retry chain is stuck |
| 10 | Node was in `Failed` state AND no new replacement attempt has started within the last 30 minutes AND total time in failing chain > 60 minutes | **Escalate** — HyperPod has given up |
| 11 | Instance id from the trigger event is missing from `list-cluster-nodes` AND `list-cluster-events` shows no new attempt for the last 30 minutes AND the most recent attempt failed | **Escalate** — instance vanished, no retry |
| 12 | HMA detection event present but no corresponding `Action:*` / replacement event in the timeline within 10 minutes | **Escalate** — HMA fired without escalating; investigate why (mismatch in node-recovery config, signal didn't classify) |
| 13 | None of the above match | **Monitor — uncategorized** (include the full timeline; flag for review) |

**Recurring-pattern verdicts (4–6) are `Escalate` even when the
individual incident is auto-recovering correctly.** The reasoning is
in your operational goals: HyperPod's resiliency repairs the symptom,
but a 3× hardware fault on the same IG is a vendor / capacity-pool
problem that auto-recovery can't fix. The verdict explanation should
explicitly say "this incident is auto-recovering, but the pattern
across the last <N> days warrants human attention" so operators
understand the verdict isn't about *this* incident's resolution.

**Time budgets are not hardcoded constants — they encode the
mental-model doc's "How long things take" section.** A single replace
takes 20–30 min; two attempts plus a slack gap = ~90 min. Don't change
these without updating the mental-model doc first.

### Phase 4 — Report (using DevOps Agent's native schema)

DevOps Agent's investigation output is structured: the terminal tool
is `write_final_investigation_report`, and the agent emits `symptom`
and `finding` records along the way that get serialized into the
final report. **Author the verdict and timeline into that schema
directly — do NOT invent a separate four-section markdown format**
(it would be at the agent's mercy during serialization and may not
survive into the final report).

The agent's schema supports these record types:

| Record type | Used for |
|---|---|
| `symptom` | Observable state the operator would notice (a node went unhealthy, an investigation was triggered, the cluster is in `Failed` state). First-class; survives serialization with title + description verbatim. |
| `finding` with `finding_type: "root_cause"` | An identified hardware/software root cause that cascades to one or more symptoms. |
| `finding` with `finding_type: "cause"` | An intermediate cause linking root_cause to symptoms. |
| `finding` with `finding_type: "hypothesis"` | An unverified explanation. |
| `investigation_gaps[]` | What the agent could not verify and would need the operator to confirm. |

**Emit exactly these records, in this order:**

1. **First `symptom`** — titled `Triage verdict: <verdict-name>` where
   `<verdict-name>` is one of `Suppress`, `Monitor — first attempt`,
   `Monitor — elevated`, `Monitor — uncategorized`, `Escalate —
   <reason>`. The description is the prose justification in the
   shape:

   ```
   Verdict: <name>

   What HyperPod is doing right now:
   <one paragraph plain English summary referencing the timeline>

   Timeline (UTC):
   <the timeline reconstructed in Phase 2, one event per line, source-tagged>

   Next re-check:
   <only for Monitor verdicts: UTC timestamp 30 min from now if "first attempt",
   15 min from now if "elevated">
   ```

   `related_resources` on this symptom: `["HyperPod cluster <name>"]`
   plus any affected instance IDs.

2. **Additional `symptom` records** — one per observable failure
   condition (e.g. "Instance i-xxxx marked unhealthy with
   NvidiaGPUUnhealthy"). These are the per-resource symptoms the
   agent would naturally produce; keep them as separate records so
   they cross-link with `cascades_to` from the findings.

3. **`finding` records** as appropriate (root cause, intermediate
   cause, hypothesis). Cross-link via `cascades_to: [<symptom-id>]`.

4. **`investigation_gaps[]`** — anything Phase 1 couldn't reach.
   Examples: `list-cluster-events` unavailable on a Slurm cluster
   without Continuous Provisioning; HMA CloudWatch log group not
   yet populated; no SSM access from the agent (always include this
   one with a note that operator can confirm via the suggested SSM
   command).

5. **`write_final_investigation_report`** — listing the verdict
   symptom FIRST in `symptoms[]`, then the per-resource symptoms.
   Findings listed under their `finding_type` arrays (`root_cause[]`,
   `cause[]`, `hypothesis[]`). `investigation_gaps[]` populated from
   step 4.

**For `Suppress` verdict:** still emit the verdict symptom (so the
operator can audit what was suppressed and why), but skip per-resource
symptoms and findings — there's nothing to root-cause.

**For `Monitor` verdicts:** the verdict symptom's description tells
the human "no action needed; HyperPod is recovering; expected
completion by HH:MM UTC. You will be notified again only if the
situation changes." This is the key UX improvement — silence is bad;
"we're watching and here's why we're not alarming you" is good.

**For `Escalate` verdicts:** include explicit operator-runnable
remediation in the verdict symptom's description, under a
`Recommended actions (operator runs these):` heading. The agent
cannot execute these; the operator must.

**Confidence annotations:** for every material claim in the verdict
description, prefix with one of `[direct]` (observed via API/log),
`[proxy]` (inferred from HMA classification or similar), or
`[unverified]` (would need on-node SSM the agent can't run). This
replaces the separate "Confidence" section.

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
