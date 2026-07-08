---
name: hyperpod-incident-triage
description: Triage stage decisions (LINKED / SKIPPED / PROCEED) for SageMaker HyperPod incident tasks. Replaces DevOps Agent's default AI correlator with explicit signature-string rules that use the concatenated Description + FailureMessage as the signature, distinguishing cross-fault-type faults on the same component (which the default AI merges). Runs at the INCIDENT_TRIAGE stage before any investigation hours are billed. The complementary INCIDENT_RCA skill `hyperpod-incident-rca` runs after this skill produces PROCEED.
metadata:
  version: "0.4.0"
  agent_types: ["INCIDENT_TRIAGE"]
---

# HyperPod incident triage skill

This skill makes the **LINKED / SKIPPED / PROCEED** decision for every
incoming HyperPod investigation task, before any RCA-stage skill runs.
DevOps Agent's default triage correlator merges incidents by component
similarity, region, and timing. **We verified empirically** that this
default merges cross-fault-type events on the same InstanceGroup —
for example, a `lifecycle-script-failed` event was LINKED to an open
`gpu-xid` investigation primary, with the platform's statusReason
citing "same instance group (worker2)" as the strong correlation
signal. The distinction between different fault types was ignored.

That's information loss. Different fault types on the same IG have
different root causes and require different operator actions.

This skill replaces that default correlator with explicit
signature-string rules. The principle:

> Two events SHOULD link if and only if they share the same
> **`<ig>:<Description + FailureMessage>`** signature. The
> concatenated fault content, as enriched by the bridge Lambda's
> `DescribeClusterEvent` call, is what distinguishes fault types —
> not a hard-coded category enum. Otherwise events with different
> Description or FailureMessage strings are distinct incidents that
> deserve separate investigations.

## Decision flow

For each incoming task, in order:

### Step 1 — Identify the trigger type

Inspect the incoming task's payload (the `description` field of the
backlog task carries the bridge-Lambda-built payload). Classify as one
of:

| Trigger type | Identifying field |
|---|---|
| `incident` — real EventBridge HyperPod event forwarded by the bridge | `data.metadata.detailType` is one of `SageMaker HyperPod Cluster State Change` / `Cluster Node Health Event` / `Cluster Event` |
| `audit` — synthetic event from the periodic-audit Lambda | `data.metadata.detailType == "HyperPod Periodic Audit"` or `data.metadata.triggerMode == "audit"` |

### Step 2 — Extract the signature

The bridge Lambda enriches every non-Info Cluster Event with the
FailureMessage retrieved via `DescribeClusterEvent`. The forwarded
task's `description` field carries both the SageMaker event
description AND the FailureMessage. Signatures are built from that
concatenation, not from regex-based category rules. Reason: the
number of possible failure modes is unbounded and hard-coded rules
are brittle when new failure types appear (verified empirically
with capacity errors that the earlier regex table classified as the
generic `instance-creation-failed:generic` bucket, silently merging
with LCS failures and other unrelated causes).

**How to build the signature:**

1. Locate the InstanceGroup:
   - `data.originalEvent.detail.EventDetails.InstanceGroupName` (Cluster Event)
   - `data.originalEvent.detail.InstanceGroupName` (Node Health / Cluster State Change)
   - Empty if the fault is cluster-level (no IG).
2. Locate the fault content:
   - `data.metadata.description` — the enriched description the bridge built. This includes:
     - `Description: <SageMaker event description>`
     - `FailureMessage: <API-returned failure message>` (if any)
     - `InstanceMetadata: <other non-null EventMetadata.Instance fields>` (if any)
   - For Node Health events: use the `HealthStatusReason + RepairAction + Recommendation` fields already in the description.
   - For Cluster State Change: use the `ClusterStatus` value.
3. **Concatenate the fault-content substring** with `<ig>` as
   `<ig>:<fault-content>`. Do NOT truncate. Do NOT hash.

Example signatures:

- `worker4:Description: Failed to provision EC2 Instance in Cluster k8-1 and InstanceGroup worker4. FailureMessage: We currently do not have sufficient capacity to launch new ml.g5.8xlarge instances. Please try again.`
- `worker2:Description: Instance i-XXXX is unhealthy. HyperPod Health Monitoring Agent (HMA) has detected fault type NvidiaGPUUnhealthy on this node and is unhealthy. Repair action: Replace.`

**Why keep full length**: verdict titles get long but stay readable.
The platform's ~20-min title-based LINK dedup uses exact string match;
we want that exact-match to distinguish "capacity for `ml.g5.8xlarge`"
from "capacity for `ml.p5.48xlarge`", which the FailureMessage
distinguishes character-for-character. Truncating would lose that
distinction.

For `audit`-type triggers, there's no single incoming signature —
audits represent "audit the whole cluster" and don't carry a fault
signature in their payload. Set incoming signature to `audit`
(single string, no colon).

### Step 3 — Read open primaries for this Agent Space

Call `aws devops-agent list-backlog-tasks` filtered to:

- `taskType=INVESTIGATION`
- `status` in `{PENDING_TRIAGE, IN_PROGRESS, PENDING_START, COMPLETED}`
- `createdAt` within the last **30 minutes** (matches the platform's
  default look-back window; broader windows would over-link)
- excluding the incoming task itself

For each candidate primary, fetch its verdict symptom (same approach
as the RCA skill's Phase 2d). Parse:

- `prior_signature_set` — the `:: (...)` suffix of the verdict title
- `prior_verdict_name` — the part between `Triage verdict: ` and ` :: `

If the candidate is `PENDING_TRIAGE` or `IN_PROGRESS` (no verdict yet),
use the task's own description to extract the same signature as
step 2 — that's the `pending_primary_signature`.

### Step 4 — Apply the decision rules

In order, stop at first match:

| # | Condition | Decision |
|---|---|---|
| 1 | Trigger type is `audit` AND there is an existing audit primary (any primary whose triggering description contains `triggerMode == audit`) within the look-back window | **LINKED** to that existing audit primary. Reason: "Periodic audit duplicates within look-back window are absorbed; rule applied: hyperpod-incident-triage audit-to-audit." |
| 2 | Trigger type is `audit` AND no audit primary in look-back window | **PROCEED**. Reason: "Scheduled periodic audit; no concurrent audit primary; runs RCA in audit mode." |
| 3 | Trigger type is `incident` AND no open primary in look-back window | **PROCEED**. Reason: "Fresh fault signature, no concurrent investigation." |
| 4 | Trigger type is `incident` AND incoming signature (exact string equality after normalization) matches an open primary's `pending_primary_signature` OR appears in an open primary's `prior_signature_set` | **LINKED** to that primary. Reason: `Same signature <sig> already covered by primary <task-id>.` |
| 5 | Default fall-through | **PROCEED**. Reason: `No matching primary; runs as new investigation.` |

> **Note (v0.4.0):** The former rule 3 (SKIP for scale-in-progress
> "lost orchestration-ready" events via a `describe-cluster` check) has
> been removed. Testing revealed a race condition: by the time the
> triage agent checks `CurrentCount != TargetCount`, the scaling
> operation has already completed. These events are now dropped at the
> bridge Lambda layer (never forwarded to the webhook) and excluded
> from the RCA skill's signature counting. If these events somehow
> reach triage (e.g. direct injection, or if the Lambda filter is
> disabled), they'll PROCEED and the RCA skill will handle them
> harmlessly — they won't trigger Escalate verdicts because the RCA
> exclusion prevents them from accumulating in `signature_count_7d`.

### Step 5 — Emit the decision

Call the platform's triage-decision tool with:

- `decision`: `LINKED` | `SKIPPED` | `PROCEED`
- `primaryTaskId`: required for LINKED, the task id from step 4
- `reason`: a one-line string starting with `[hyperpod-incident-triage]`
  followed by the rule that fired and the (possibly truncated) signature
  strings, e.g.
  `[hyperpod-incident-triage] rule 4: incoming signature matches primary <task-id>; signature starts with "worker4:Description: Failed to provision EC2 Instance ... FailureMessage: We currently do not have sufficient capacity to launch new ml.g5.8xlarge..."`.
  For rule-4 LINKs, include the first ~200 characters of the matching
  signature so operators auditing the LINK can confirm the match.

The reason string is what shows up in the LINKED task's `statusReason`
field in `list-backlog-tasks`, so make it operator-readable.

## Why this skill does NOT do Phase 1 gather

Unlike the RCA skill, the triage skill **does not** read
`describe-cluster`, paginate `list-cluster-events`, or query CloudWatch
Logs. Triage is supposed to be fast — the platform expects a decision
back in seconds. Heavy API gather would slow every incoming task.

The trade-off: triage decisions are based on **the incoming task's
payload + the open primaries it can list**, not on the full cluster
state. This is fine because:

- The signature extraction needs only the event description text
- The "open primary" check needs only `list-backlog-tasks`, which is
  fast and paginates predictably
- The full timeline / recurrence statistics / Resolved closure logic
  all live in the RCA skill, which runs only when this skill says
  PROCEED

If the triage decision is wrong (link when shouldn't, or proceed when
should link), the operator can manually unlink via the Agent Space
console (UG-documented), and the RCA skill's signature-set logic
serves as a backstop that still produces correct verdicts at the
investigation stage.

## Anti-patterns this skill protects against

1. **Cross-fault-type LINK on the same IG.** Default platform AI merges
   a `lifecycle-script-failed` event into an open `gpu-xid` primary
   because both touch worker2. This skill keeps them separate because
   the concatenated `Description + FailureMessage` strings differ →
   distinct signatures → rule 4 doesn't fire.
2. **Cross-IG LINK of the same fault type.** `Xid 74 on worker2` and
   `Xid 74 on worker3` are distinct hardware faults. Since the IG is
   part of the signature (`worker2:...` vs `worker3:...`), rule 4
   doesn't fire.
3. **Cross-SKU capacity errors.** Two capacity errors for different
   instance types (`ml.g5.8xlarge` vs `ml.p5.48xlarge`) produce
   different FailureMessage strings → different signatures → rule 4
   doesn't fire. Was previously merged when we used rule-based
   `capacity-insufficient:generic` category keys.
4. **Audit-mode noise.** Multiple periodic audits within the look-back
   window LINK together (rule 1), so only one audit-mode RCA runs per
   look-back window. The first audit produces the verdict; subsequent
   audits within the window are absorbed.
5. **First-ever incidents on a quiet cluster** still PROCEED (rule 3),
   so the first signal always triggers an investigation.
6. **Scale-in-progress noise.** During customer-initiated
   `UpdateCluster` operations (scale-up or scale-down), HyperPod
   emits `Warn`-level events like `"N node(s) lost orchestration-ready
   status. Current: X/Y orchestration-ready across N instance
   group(s)."` — with the misleading FailureMessage
   `"Request to service failed. If failure persists after retry,
   contact customer support."` These events are now **dropped at the
   bridge Lambda** before reaching the webhook (they never create
   backlog tasks). Additionally, the RCA skill excludes them from
   `signature_count_7d` so they don't contribute to Escalate
   verdicts if discovered during audit-mode `list-cluster-events`
   walks.
