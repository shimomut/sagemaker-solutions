---
name: hyperpod-incident-triage
description: Triage stage decisions (LINKED / SKIPPED / PROCEED) for SageMaker HyperPod incident tasks. For incident-mode triggers, uses concatenated Description + FailureMessage signature strings to distinguish cross-fault-type faults on the same component (which the platform's default AI correlator merges). For audit-mode triggers, computes a full cluster signature (fault chain + CrashLoopBackOff pods + NotReady nodes) and only LINKs when the signature is unchanged since the last audit primary — a periodic audit that discovers a new issue is never absorbed into a stale primary. Runs at the INCIDENT_TRIAGE stage before any RCA investigation hours are billed. The complementary INCIDENT_RCA skill `hyperpod-incident-rca` runs after this skill produces PROCEED.
metadata:
  version: "0.6.1"
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
signature-based rules. Two principles:

> **Incident mode**: two events SHOULD link if and only if they share
> the same **`<ig>:<Description + FailureMessage>`** signature. The
> concatenated fault content, as enriched by the bridge Lambda's
> `DescribeClusterEvent` call, is what distinguishes fault types —
> not a hard-coded category enum. Otherwise events with different
> Description or FailureMessage strings are distinct incidents that
> deserve separate investigations.

> **Audit mode**: a periodic audit should only be LINKED / SKIPPED
> when the **cluster signature is unchanged since the last audit**.
> The audit signature is a set summarizing the open fault chains,
> CrashLoopBackOff pods, and NotReady nodes. If any element of the
> set has changed, the audit runs a fresh RCA — a new issue is never
> silently absorbed into a stale primary.

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

### Step 2a — Extract the incident-mode signature (incident triggers only)

The bridge Lambda enriches every non-Info Cluster Event with the
FailureMessage retrieved via `DescribeClusterEvent`. The forwarded
task's `description` field carries both the SageMaker event
description AND the FailureMessage. Signatures are built from that
concatenation, not from regex-based category rules. Reason: the
number of possible failure modes is unbounded and hard-coded rules
are brittle when new failure types appear.

**How to build the signature:**

1. Locate the InstanceGroup:
   - `data.originalEvent.detail.EventDetails.InstanceGroupName` (Cluster Event)
   - `data.originalEvent.detail.InstanceGroupName` (Node Health / Cluster State Change)
   - Empty if the fault is cluster-level (no IG).
2. Locate the fault content:
   - `data.metadata.description` — the enriched description the bridge built. Includes `Description:`, `FailureMessage:`, `InstanceMetadata:`.
   - Node Health: use `HealthStatusReason + RepairAction + Recommendation`.
   - Cluster State Change: use `ClusterStatus`.
3. Concatenate: `<ig>:<fault-content>`. Do NOT truncate. Do NOT hash.

Example signatures:

- `worker4:Description: Failed to provision EC2 Instance in Cluster k8-1 and InstanceGroup worker4. FailureMessage: We currently do not have sufficient capacity to launch new ml.g5.8xlarge instances. Please try again.`
- `worker2:Description: Instance i-XXXX is unhealthy. HyperPod Health Monitoring Agent (HMA) has detected fault type NvidiaGPUUnhealthy on this node and is unhealthy. Repair action: Replace.`

**Why keep full length**: verdict titles get long but stay readable.
The platform's ~20-min title-based LINK dedup uses exact string match;
we want that exact-match to distinguish "capacity for `ml.g5.8xlarge`"
from "capacity for `ml.p5.48xlarge`", which the FailureMessage
distinguishes character-for-character. Truncating would lose that
distinction.

### Step 2b — Compute the audit-mode signature (audit triggers only)

Audit triggers do NOT carry a per-event signature. Instead, triage
computes a **cluster-wide audit signature** by inspecting three
sources. This is the key change vs. v0.4.0: triage now bases its
LINK/PROCEED decision on **actual current state**, not on the
existence of a prior audit primary within an arbitrary time window.
That fixes the failure mode where a crashloop that appeared 5
minutes after the last audit's primary was silently absorbed as a
"duplicate."

The audit signature is the **sorted union of three sets**, joined
with `|` as a stable string:

1. **Fault-chain set.** From `list-cluster-events` in the last 4h,
   emit `fault:<ig>:<truncated-signature-first-120-chars>` for each
   Error/Warn event. Same signature-string construction as Step 2a,
   truncated to 120 chars to keep the audit signature bounded.
   Excludes `Info` events. Excludes events whose Description contains
   `"lost orchestration-ready status"` (scale-in-progress noise —
   see anti-pattern 6).
2. **CrashLoopBackOff set.** From `kubectl get pods -A -o json`:
   for each Pod with `status.containerStatuses[].state.waiting.reason == "CrashLoopBackOff"`,
   emit `crashloop:<namespace>/<pod>:<container>`. Uses only the
   pod identity — NOT the restart count, NOT the age — so a
   currently-crashlooping pod produces a stable signature across
   consecutive audits.
3. **NotReady-node set.** From `kubectl get nodes -o json`: for each
   node whose `status.conditions[type=Ready].status != "True"`, emit
   `notready:<node-name>`. Uses only the node name, not the duration
   — same stability principle as (2).

**Namespace filter for the CrashLoopBackOff set.** The trigger
payload's `data.metadata.k8sChecks.ignoreNamespaces` (if present)
lists namespaces to skip entirely. Pods in those namespaces are
excluded from the CrashLoopBackOff set — they don't contribute to
the signature at all. `systemNamespaces` are NOT filtered here (they
still contribute to the signature so a system-workload crashloop
still forces a fresh RCA); the system-vs-customer tag is applied
inside RCA.

**Result:** the audit signature is a deterministic string like

```
crashloop:crashloop-test/crashloop-canary:fail|fault:worker1:Description: Lifecycle scripts did not run...|notready:hyperpod-i-abc
```

Empty sets produce an empty audit signature. That's fine — a
healthy cluster's signature is `""`, and subsequent healthy audits
match on `""`.

**Cost.** The two kubectl calls add ~1–3 sec per audit fire.
`list-cluster-events` is already paginated by the bridge for
enrichment; the 4-hour window is bounded by rows-fetched cap
(~200 events) so it typically returns in <2 sec. Total triage
overhead: ~3–5 sec. This is per-audit, whether it results in LINK,
SKIP, or PROCEED.

**If `data.metadata.k8sChecks` is absent or has `enabled: false`**
in the audit payload: skip the kubectl portion. The audit
signature reduces to just the fault-chain set. This keeps triage
functional when k8s checks are disabled at the audit-stack level.

### Step 3 — Read recent audit primaries and retrieve their signatures

Call `aws devops-agent list-backlog-tasks` filtered to:

- `taskType=INVESTIGATION`
- Title `HyperPod periodic audit: <cluster>` (audit-mode dedup only
  considers other audit primaries)
- `createdAt` within the last **60 minutes** (widened from the
  v0.4.0 30-min window because it's now safe — the LINK decision is
  gated on signature equality, not on the mere existence of a
  primary within the window)
- excluding the incoming task itself

For each candidate primary, retrieve its recorded audit signature:

1. Look for a symptom record whose title begins with
   `Audit signature:`. The description contains the full signature
   string (which may be long). The skill emits exactly one such
   record per audit primary in Step 5. If the primary is from before
   v0.5.0 or the record is missing, treat its signature as `null`
   (unknown) — that primary won't match any incoming signature.
2. Also record the primary's `status`
   (`PENDING_TRIAGE` / `IN_PROGRESS` / `COMPLETED` / etc.).

For incident-mode triggers, use the v0.4.0 approach: fetch the
verdict symptom's title (`Triage verdict: <name> :: (<signature-set>)`)
and parse `prior_signature_set`.

### Step 4 — Apply the decision rules

**HARD CONSTRAINTS — THESE OVERRIDE ANY OTHER REASONING.**

1. **The DEFAULT decision for an `audit` trigger is PROCEED.** You
   must have a **positive signature match** OR a **concurrent
   in-progress primary** to justify anything else.

2. **NEVER LINK an audit task to a `PENDING_TRIAGE`, `IN_PROGRESS`,
   or `PENDING_START` primary.** LINK re-activates the primary and
   creates a feedback loop where the primary never finishes. The
   correct decision in that case is SKIP (rule 1). LINK is only
   valid against a primary that has already reached a terminal
   state (`COMPLETED` etc.).

3. **"Signature match" means exact byte-for-byte string equality**
   with a prior audit primary's *recorded* audit signature (the one
   stored in that primary's `Audit signature:` symptom record). Both
   empty strings match each other.

Do NOT infer a signature match from any of these:
- Same cluster name.
- Same task title (they no longer collide by design — the audit
  Lambda includes a per-fire timestamp in the title).
- Same `triggerMode`.
- Task recency ("triggered N minutes after the last one").

If you cannot retrieve a prior audit primary's recorded signature
because the symptom record is missing OR unreadable OR the primary
predates v0.6.0, its signature is `null` and it does NOT match the
incoming signature. Do not fall back to any other heuristic. Do
not LINK on the basis of "duplicate audit" reasoning.

Primary `status` is used **only** for rule 1 (SKIP if concurrent
in-progress). Rules 2/3 ignore status.

Apply the rules in order, stop at first match:

| # | Condition | Decision |
|---|---|---|
| 1 | Trigger is `audit` AND there exists an audit primary whose `status` is **strictly** `IN_PROGRESS` OR `PENDING_START` (concurrent RCA already running) | **SKIPPED**. Reason: `Concurrent periodic-audit RCA already running (primary <task-id>, status=<status>); skipping to avoid concurrent audit executions. hyperpod-incident-triage rule 1.` **Use SKIPPED, NOT LINKED**: LINK re-activates the primary and creates a feedback loop. SKIP terminates cleanly. The concurrent primary will produce its own verdict; this fire is discarded. |
| 2 | Trigger is `audit` AND there exists a prior audit primary (any non-in-progress status) whose recorded audit signature is **exact byte-for-byte equal** to the incoming audit signature (both empty is a match) | **LINKED** to that primary. Reason: `Audit signature match with primary <task-id>. Incoming sig: "<first 100 chars>". Prior sig: "<first 100 chars>". hyperpod-incident-triage rule 2.` |
| 3 | Trigger is `audit` AND no signature match (incoming signature is new relative to every prior recorded signature) | **PROCEED**. Reason: `New audit signature; no matching prior primary. Incoming sig: "<first 100 chars>". hyperpod-incident-triage rule 3.` |
| 4 | Trigger is `incident` AND no open primary in look-back window | **PROCEED**. Reason: "Fresh fault signature, no concurrent investigation." |
| 5 | Trigger is `incident` AND incoming signature matches an open primary's `pending_primary_signature` OR appears in an open primary's `prior_signature_set` | **LINKED** to that primary. Reason: `Same signature <sig> already covered by primary <task-id>.` |
| 6 | Default fall-through | **PROCEED**. Reason: `No matching primary; runs as new investigation.` |

**Why rule 1 uses SKIPPED, not LINKED.** DevOps Agent's platform
re-invokes a primary as `IN_PROGRESS` on every incoming LINK. If
the incoming audit LINKed to the in-progress primary, the platform
would notify the primary of the new LINK, flip its status back to
`IN_PROGRESS`, and extend its runtime. Over a 15-minute audit
cadence, back-to-back LINKs can keep a primary in-progress
indefinitely — that's the failure mode observed in the v0.5.x
runs where a primary stayed IN_PROGRESS for 68+ minutes as new
LINKs kept arriving.

SKIPPED terminates the incoming task cleanly without re-activating
the primary. The concurrent primary continues its RCA
uninterrupted, produces its verdict, then transitions to COMPLETED
normally. The skipped audit fire is discarded — its cluster state
observation is lost, but that's acceptable because the in-progress
primary IS observing the cluster at approximately the same time,
and the next audit fire (15 min later) will re-check.

**Design note — evolution from v0.5 (concurrency LINK) → v0.6.0
(signature-only) → v0.6.1 (signature + concurrency SKIP).**

- v0.5.0 / v0.5.1 tried LINK for concurrent primaries. This failed
  because DevOps Agent's platform re-invokes a primary as
  `IN_PROGRESS` on every incoming LINK — creating a feedback loop
  where the primary never finishes.
- v0.6.0 removed the concurrency rule entirely and made every audit
  either LINK-on-signature-match or PROCEED. This fixed the
  feedback loop but allowed truly-concurrent RCAs to run in parallel
  when audits fired seconds apart.
- v0.6.1 (current) restores concurrency awareness but as **SKIP**
  (not LINK). SKIP terminates the incoming task without touching the
  in-progress primary, so no feedback loop. The concurrent primary
  finishes normally; the skipped audit is discarded.

**Why SKIP is safe here.** The in-progress primary is observing the
cluster at approximately the same time as the skipped audit would
have. The 15-minute audit cadence guarantees another fire soon,
which will run against the next COMPLETED primary via rule 2 or
rule 3. No signal is permanently lost.

**Worked example A — crashloop discovery when primary is COMPLETED:**

Scenario: A `COMPLETED` audit primary from 17:19 has recorded
audit signature `""` (cluster was healthy). A new audit fires at
19:37 with computed signature
`crashloop:crashloop-test/canary:fail`.

**v0.6.1 decision:**
1. Rule 1 check: primary's status is `COMPLETED`, not
   `IN_PROGRESS` / `PENDING_START` → rule 1 does NOT fire.
2. Rule 2 check: primary's recorded signature = `""` ≠ incoming
   `crashloop:...` → rule 2 does NOT fire.
3. Rule 3: PROCEED. RCA runs, inspects the crashloop, emits Escalate.

**Worked example B — concurrent audit already running:**

Scenario: An audit primary from 19:37 is currently
`IN_PROGRESS` (its RCA has been running for ~2 min and hasn't yet
recorded its `Audit signature:` symptom). A new audit fires at
19:39 with computed signature
`crashloop:crashloop-test/canary:fail`.

**v0.6.1 decision:**
1. Rule 1 check: primary's status is `IN_PROGRESS` → rule 1 fires.
   Decision: **SKIPPED**. The 19:37 primary continues undisturbed;
   the 19:39 fire is discarded. When the 19:37 primary completes,
   the next audit fire (from the scheduler) will find a `COMPLETED`
   primary and fall through to rule 2 / rule 3 as appropriate.

**Worked example C — same-signature audit while primary is COMPLETED:**

Scenario: A `COMPLETED` audit primary from 20:00 has recorded
audit signature `crashloop:crashloop-test/canary:fail` (it Escalated
on the crashloop). A new audit fires at 20:15 with the same
computed signature — the crashloop is still active, no new problem.

**v0.6.1 decision:**
1. Rule 1 check: primary's status is `COMPLETED` → rule 1 does NOT
   fire.
2. Rule 2 check: recorded signature `crashloop:...` == incoming
   `crashloop:...` → rule 2 fires. Decision: **LINKED** to the
   20:00 primary. No new email; the operator already knows.

### Step 5 — Emit the decision AND record the audit signature

Call the platform's triage-decision tool with:

- `decision`: `LINKED` | `SKIPPED` | `PROCEED`
- `primaryTaskId`: required for LINKED, the task id from Step 4
- `reason`: a one-line string starting with `[hyperpod-incident-triage]`
  followed by the rule that fired and (for audit-mode rules 2 and 3)
  the first ~200 characters of the audit signature so operators
  auditing the decision can confirm what changed.

**Additionally, for every audit-mode task that ends up as a primary
(PROCEED that becomes IN_PROGRESS), emit a symptom record**:

```
{
  "type": "symptom",
  "id": "audit-signature-record",
  "title": "Audit signature: <first 120 chars of signature string, or '(empty — cluster quiet)'>",
  "description": "<full audit signature string, potentially long>",
  "related_resources": ["HyperPod cluster <name>"]
}
```

This is the record subsequent triage runs read in Step 3 to
retrieve `prior_audit_signature`. **Do not conflate this record with
the RCA's verdict symptom** — the RCA skill emits its own
`Triage verdict:` symptom later. Both symptoms coexist on the same
primary.

The reason string is what shows up in the LINKED / SKIPPED task's
`statusReason` field in `list-backlog-tasks`, so make it
operator-readable.

## Why triage does the kubectl calls (and RCA no longer duplicates them)

Prior versions (up to v0.4.0) kept triage lightweight and pushed all
cluster inspection to RCA. That produced the failure mode we
observed 2026-07-09: two audit tasks fired 68 minutes apart, the
second one saw a fresh CrashLoopBackOff pod that appeared in
between, but triage LINKED the second task to the first primary
without inspecting anything — the crashloop was silently absorbed.
Zero journal records on the LINKED task confirmed RCA never ran.

The v0.5.0 design accepts a small triage cost (~3–5 sec of API
calls per audit) to guarantee that **triage's LINK decision is
based on actual current state**. This is the same shape principle
used by the k8sChecks payload block: **push structure into cheap
pre-computation, keep the expensive-reasoning stage focused on
judgment, not on discovery.**

Costs:

- Two kubectl calls (`get pods -A`, `get nodes`) + one
  `list-cluster-events` page: ~3–5 sec per audit fire, no LLM
  tokens.
- Runs on every audit, including LINK / SKIP cases (unavoidable —
  the signature IS the decision input).
- On a healthy cluster: signature is `""` for every audit, all
  subsequent audits SKIP via rule 2. Roughly 1 primary/hour of RCA
  cost instead of 1 primary/audit (rate(15 minutes) = 4/hour).
- On a cluster with a persistent crashloop: signature is stable, so
  the second-and-onward audits SKIP via rule 2. The first audit
  after the pod appears PROCEEDs; the operator gets one email; the
  next 4h of periodic audits SKIP until either the pod recovers
  (signature reverts to `""` → new PROCEED, closure email) or a new
  problem appears (signature changes → new PROCEED).

## Anti-patterns this skill protects against

1. **Cross-fault-type LINK on the same IG.** Default platform AI merges
   a `lifecycle-script-failed` event into an open `gpu-xid` primary
   because both touch worker2. This skill keeps them separate because
   the concatenated `Description + FailureMessage` strings differ →
   distinct signatures → rule 5 doesn't fire.
2. **Cross-IG LINK of the same fault type.** `Xid 74 on worker2` and
   `Xid 74 on worker3` are distinct hardware faults. Since the IG is
   part of the signature (`worker2:...` vs `worker3:...`), rule 5
   doesn't fire.
3. **Cross-SKU capacity errors.** Two capacity errors for different
   instance types (`ml.g5.8xlarge` vs `ml.p5.48xlarge`) produce
   different FailureMessage strings → different signatures → rule 5
   doesn't fire.
4. **Audit that misses a new issue** — the v0.4.0 failure mode.
   Fixed by v0.6.0's signature-first design: an audit LINKS only
   when the incoming audit signature is byte-for-byte equal to a
   prior primary's recorded signature. A newly-appeared crashloop,
   NotReady node, or fault event changes the signature → rule 2 →
   fresh RCA. The primary's `status` (COMPLETED vs. IN_PROGRESS) is
   deliberately ignored — see the design note in Step 4.
5. **First-ever incidents on a quiet cluster** still PROCEED (rule 4),
   so the first signal always triggers an investigation.
6. **Scale-in-progress noise.** During customer-initiated
   `UpdateCluster` operations, HyperPod emits `Warn`-level events
   like `"N node(s) lost orchestration-ready status..."` with the
   misleading FailureMessage `"Request to service failed..."`.
   These are dropped at the bridge Lambda before reaching the
   webhook. The audit signature's fault-chain set also excludes
   them by Description match. The RCA skill excludes them from
   `signature_count_7d`.
