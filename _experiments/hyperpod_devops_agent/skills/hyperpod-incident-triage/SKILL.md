---
name: hyperpod-incident-triage
description: Triage stage decisions (LINKED / SKIPPED / PROCEED) for SageMaker HyperPod incident tasks. Replaces DevOps Agent's default AI correlator with explicit (InstanceGroup, fault-category, fault-key) signature-set rules that distinguish cross-category faults on the same component (which the default AI merges). Runs at the INCIDENT_TRIAGE stage before any investigation hours are billed. The complementary INCIDENT_RCA skill `hyperpod-incident-rca` runs after this skill produces PROCEED.
metadata:
  version: "0.1.0"
  agent_types: ["INCIDENT_TRIAGE"]
---

# HyperPod incident triage skill

This skill makes the **LINKED / SKIPPED / PROCEED** decision for every
incoming HyperPod investigation task, before any RCA-stage skill runs.
DevOps Agent's default triage correlator merges incidents by component
similarity, region, and timing. **We verified empirically** that this
default merges cross-category faults on the same InstanceGroup — for
example, a `lifecycle-script-failed` event was LINKED to an open
`gpu-xid` investigation primary, with the platform's statusReason
citing "same instance group (worker2)" as the strong correlation
signal. The categorical distinction was ignored.

That's information loss. Different fault categories on the same IG
have different root causes and require different operator actions.

This skill replaces that default correlator with explicit signature-set
rules. The principle:

> Two events SHOULD link if and only if they share the same
> `(InstanceGroup, fault-category, fault-key)` signature AND would
> drive the same verdict. Otherwise they're distinct incidents that
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

Use the same category rules as the RCA skill's Phase 2b (see
[hyperpod-incident-rca's SKILL.md](../hyperpod-incident-rca/SKILL.md)
for the full table). The categories and keys are identical:

| Category | Match condition | `<key>` |
|---|---|---|
| `gpu-xid` | description matches `NVRM: Xid (...): N` | `N` |
| `gpu-ecc-uce` | description cites ECC uncorrectable / UCE | empty |
| `efa-health-check` | description contains `"EFA health checks did not run successfully"` | empty |
| `lifecycle-script-failed` | description matches `Instance lifecycle script execution for ... has Failed` | exit code if present, else empty |
| `capacity-insufficient` | description contains `"insufficient capacity"` or `"sufficient capacity in the Availability Zone"` | instance type if extractable, else empty |
| `instance-creation-failed` | description matches `"Failed to provision EC2 Instance"` AND no more-specific category matched | `"generic"` |
| `node-health-unhealthy` | detail-type is `Cluster Node Health Event` AND `HealthSummary.HealthStatus` is `Unhealthy` or `Degraded` | the `HealthStatusReason` value |
| `cluster-failed` | detail-type is `Cluster State Change` AND `ClusterStatus` is `Failed` | the status value |
| `cluster-rollingback` | detail-type is `Cluster State Change` AND `ClusterStatus` is `RollingBack` | empty |
| `unclassified` (fallback) | none of the above matched | first 30 alphanumeric chars of description |

Extract the InstanceGroup from `detail.InstanceGroupName` (Cluster
State Change) or `detail.EventDetails.InstanceGroupName` (Cluster
Event) or `detail.InstanceGroupName` (Node Health). Empty if
cluster-level.

The result is the **incoming signature**: a single tuple
`(<category>, <key>, <ig>)`.

For `audit`-type triggers, there's no single incoming signature —
audits represent "audit the whole cluster" and don't carry a fault
signature in their payload. Set incoming signature to `audit:*:*`.

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
| 4 | Trigger type is `incident` AND incoming signature equals an open primary's `pending_primary_signature` OR appears in an open primary's `prior_signature_set` | **LINKED** to that primary. Reason: "Same `(IG, category, key)` signature `<sig>` is already covered by primary <task-id>." |
| 5 | Trigger type is `incident` AND incoming signature is `(unclassified, ...)` AND no existing primary already has the same `unclassified` signature | **PROCEED**. Reason: "Unclassified fault signature; new investigation. Operator should review and extend the triage skill's category table." |
| 6 | Default fall-through | **PROCEED**. Reason: "No matching primary; runs as new investigation." |

### Step 5 — Emit the decision

Call the platform's triage-decision tool with:

- `decision`: `LINKED` | `SKIPPED` | `PROCEED`
- `primaryTaskId`: required for LINKED, the task id from step 4
- `reason`: a one-line string starting with `[hyperpod-incident-triage]`
  followed by the rule that fired and the relevant signatures, e.g.
  `[hyperpod-incident-triage] rule 4: incoming (worker2:gpu-xid:74) matches primary ki-abcd1234 (worker2:gpu-xid:74)`.

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

1. **Cross-category LINK on the same IG.** Default platform AI merges
   `lifecycle-script-failed` into `gpu-xid` because both touch
   worker2. This skill keeps them separate because their `category`
   differs → distinct signatures → rule 4 doesn't fire.
2. **Cross-IG LINK of the same Xid.** `Xid 74 on worker2` and
   `Xid 74 on worker3` are distinct hardware faults; they share the
   category and key but differ on IG. This skill keeps them separate.
3. **Audit-mode noise.** Multiple periodic audits within the look-back
   window LINK together (rule 1), so only one audit-mode RCA runs per
   look-back window. The first audit produces the verdict; subsequent
   audits within the window are absorbed.
4. **First-ever incidents on a quiet cluster** still PROCEED (rule 3),
   so the first signal always triggers an investigation.
