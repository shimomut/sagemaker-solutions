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

## Trigger modes

The skill is loaded from two trigger sources, and Phase 1 / Phase 3
behavior differs slightly between them:

| Mode | Trigger | Scope |
|---|---|---|
| **Incident mode** | Webhook fire from the bridge Lambda (an EventBridge HyperPod event passed the noise filter). The investigation context carries `clusterName` and usually an `instanceId`. | Focused on the specific incident referenced in the trigger. |
| **Audit mode** | Scheduled `TIME_BASED` trigger (rate(15 minutes)) creating a task against this skill with no per-incident context. | Scan the cluster(s) configured for this Agent Space for any in-flight or recently-resolved fault chains, and re-classify each one. Catches: (1) `Monitor` incidents that have now succeeded (emit `Resolved`), (2) `Monitor` incidents stuck past their re-check budget (escalate), (3) recurring patterns that didn't trigger an EventBridge event recently but persist statistically. |

In both modes the same Phase 1 / Phase 2 / Phase 3 / Phase 4 logic
applies. The differences are noted inline below.

### Phase 1 — Gather (run in parallel)

For the incident referenced in the trigger event (cluster name + optional
instance id), collect these in parallel. **Do not stop on a single
signal — gather all of them before classifying.**

**Audit mode**: the trigger payload won't carry a cluster name or
instance id. Use the cluster(s) reachable from this Agent Space's AWS
account association (typically just one HyperPod cluster — discover
it via `sagemaker list-clusters`). For each cluster, run the full
Phase 1 gather. Then in Phase 3, classify per open fault chain found
in the cluster-events window, not per single trigger.

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

### Phase 2b — Categorize every fault event

HyperPod faults are not just NVIDIA GPU Xid errors. Lifecycle script
failures, capacity errors, EFA health-check failures, Neuron errors,
and generic instance-provisioning failures are all valid drivers of
HyperPod replacements and operator notifications. Categorize each
fault event (Error/Warn cluster event or HMA detection within the
4h window for signature-set computation, and within the 7d window
for recurrence statistics) into one of these categories:

| Category | Match condition | `<key>` extraction |
|---|---|---|
| `gpu-xid` | HMA detection or kernel log matching `NVRM: Xid (...): N` | Xid code `N` (e.g. `74`) |
| `gpu-ecc-uce` | HMA detection citing ECC uncorrectable error / UCE | empty |
| `gpu-row-remap` | DCGM `row_remap_pending` field crossed threshold | empty |
| `neuron-mismatch` | HMA detection on Trainium/Inferentia node, device count mismatch via `neuron-ls` | detection subtype if present, else empty |
| `efa-health-check` | Cluster event text contains `"EFA health checks did not run successfully"` | empty |
| `lifecycle-script-failed` | Cluster event text matches `Instance lifecycle script execution for ... has Failed` | exit code if present in event metadata, else empty |
| `capacity-insufficient` | Cluster event text contains `"insufficient capacity"` or `"We currently do not have sufficient capacity"` | instance type if extractable, else empty |
| `instance-creation-failed` | Cluster event text matches `"Failed to provision EC2 Instance"` AND none of the more specific categories above matched | `"generic"` |
| `cluster-failed` | `describe-cluster` returns `ClusterStatus: Failed` | the ClusterStatus value |
| `cluster-rollingback` | `describe-cluster` returns `ClusterStatus: RollingBack` | empty |
| `node-notready-eks` | EKS API / kubectl shows the node `NotReady` for >5 min with no concurrent HMA detection or cluster event explaining it | EKS NodeCondition reason if present, else empty |
| **`unclassified`** (fallback) | Error/Warn cluster event or HMA detection that did not match any rule above | first 50 characters of the event description, lowercased + non-alphanumerics replaced with `-`, then truncated to 30 chars |

**The `unclassified` bucket is the safety net.** Every fault event
must end up with some `(category, key, ig)` signature so the
signature-set comparison and platform verdict-title dedup work
deterministically. If new categories appear in field usage, extend
the table above before rerunning. The skill MUST emit an
`investigation_gap` record when it produces any `unclassified`
signatures, naming the offending event description text — so the
operator can request a skill update.

### Phase 2c — Compute recurrence statistics

Over the 7-day `list-cluster-events` window from Phase 1 (and HMA
CloudWatch stream over the same window), compute and record (used by
Phase 3 rules 7–9):

- `replacements_7d_total` — count of `Replace` actions / replacement-
  started cluster events across the whole cluster in the last 7 days.
- `replacements_7d_by_group[<ig>]` — same, partitioned by InstanceGroup.
- `replacements_24h_total` — same metric, 24h window.
- `signature_count_7d[(<category>, <key>, <ig>)]` — count of distinct
  fault events with the same `(category, key, ig)` tuple in the last
  7 days. Use the categorization from Phase 2b. **Exclude
  `category="unclassified"` from this map** — recurring-pattern
  rules (Phase 3 rule 7) should only fire on signatures we
  understand.

Include these counts in the verdict description's "What HyperPod is
doing right now" paragraph when they're ≥2 — even if the verdict
itself doesn't change, the operator should see the count.

### Phase 2d — Compute the signature set and read the prior audit

The signature set drives both verdict-title generation (which the
platform's 30-min dedup uses) and the rule-3 staleness check (which
prevents long-window re-Escalate spam). Compute:

- `current_signature_set` — sorted, deduplicated set of strings of
  the form `"<ig>:<category>:<key>"` for every distinct fault event
  in the 4-hour window, using the categorization from Phase 2b.
  Examples:
  - `{"worker2:gpu-xid:74", "worker3:gpu-xid:79"}` (two different Xids on two IGs)
  - `{"worker2:gpu-xid:74", "worker2:lifecycle-script-failed:"}` (GPU fault + LCS failure on the same IG)
  - `{":cluster-failed:Failed"}` (cluster-level fault — IG slot empty)

  Render in the verdict title as
  `(worker2:gpu-xid:74, worker3:gpu-xid:79)` — comma-separated,
  sorted lexically, no spaces around the colons. Empty `<ig>` is
  rendered as nothing (`(:cluster-failed:Failed)` → `(cluster-failed:Failed)`).
- `current_most_recent_event_at` — the latest `EventTime` of any
  Error/Warn cluster event or HMA detection within the window.

**Reading the prior audit's verdict** (audit mode only — skip for
incident mode):

1. Call `aws devops-agent list-backlog-tasks --agent-space-id <id>`.
2. Find the most recent task whose `taskType=INVESTIGATION`, whose
   `title` starts with `Triage verdict: ` (i.e. it's a prior audit
   that produced a verdict — investigation-mode tasks have a
   different title shape), and whose `createdAt` is within the
   last 24 hours.
3. Parse the prior verdict's signature set from the title's `:: (...)`
   suffix. Parse the prior `most_recent_event_at` from the prior
   verdict's description (the "Timeline (UTC)" section lists events
   with timestamps).
4. If found, hold these as `prior_signature_set` and
   `prior_most_recent_event_at` for use in rule 3.
5. If not found (first-ever audit, or all prior audits aged out),
   skip rule 3 entirely — fall through to the normal rules.

If `list-backlog-tasks` returns no matching prior audit, do not
mistake the absence for "no events" — rule 1 (no fault events in
4h window) handles the no-events case independently.

### Phase 3 — Classify

Apply the rules below **in order**. Stop at the first match.

**Audit mode**: classify each open fault chain found in the
cluster-events window independently. Emit one verdict per chain
(plus one `Suppress — periodic audit, no open incidents` if no
chains are open). A fault chain is "open" if it had a fault event
within the last 4 hours and has not yet emitted a successful
`Running` transition + 30 min clean-window.

The recurring-pattern rules (7–9) are checked **before** the
single-incident rules (10–13) — a node that's auto-recovering for the
3rd time this week should be flagged as a pattern, not silently
classified as `Monitor — first attempt`.

| # | Signal pattern | Verdict |
|---|---|---|
| 1 | **Audit mode** AND no fault events in the 4-hour window AND no `Monitor` fault chain still open | **Suppress — periodic audit, no open incidents** (skip Phase 4 entirely or emit a minimal record; nothing actionable) |
| 2 | A previously-`Monitor` fault chain now shows the affected instance(s) back in `Running` AND no new HMA detection for that instance in the last 30 min AND cluster status is `InService` | **Resolved — auto-recovery succeeded** (operator gets a closure email; include the original detection time and total elapsed) |
| 3 | **Audit mode** AND the set of `(InstanceGroup, Xid-signature)` pairs that would drive an Escalate verdict is **unchanged** since the previous audit's primary verdict for this Agent Space, AND no fault event newer than the previous audit's `most_recent_event_at` exists, AND no `Monitor` fault chain is still open, AND none of the prior `Resolved` conditions apply | **Suppress — periodic audit, evidence is stale** (filtered by email notifier). See "Computing the signature set" and "Reading the prior audit" below — this rule prevents the audit from re-emailing identical `Escalate` verdicts every 15 min for the full 7 days that a stale event burst remains in the cluster-events window. A NEW signature, a NEW InstanceGroup, or a NEW fault event since the prior audit advances state and re-opens classification through the other rules. |
| 4 | Trigger detail-type is `Cluster Event` with `EventLevel=Info` and the timeline shows no node-health activity | **Suppress** |
| 5 | Cluster status is `Failed` or `RollingBack` | **Escalate** (cluster-level) |
| 6 | `NodeRecovery=None` on the cluster AND a node has been marked `Action:*` / `UnschedulablePending*` AND no replacement has started within 5 minutes | **Escalate** — auto-recovery is off; operator must trigger replacement |
| 7 | `signature_count_7d[(<category>, <key>, <ig>)] ≥ 3` for ANY signature whose `category != "unclassified"` — same categorized fault has driven ≥3 replacements on the same InstanceGroup in the last 7 days (auto-recovery may be succeeding each time). Covers all fault types in Phase 2b's category table — GPU Xid, lifecycle-script failures, capacity exhaustion, EFA health-check failures, etc. | **Escalate — recurring `<category>` pattern**: HyperPod is repairing the symptom, but the underlying cause hasn't gone away. Verdict name includes the category — e.g. `Escalate — recurring gpu-xid pattern`, `Escalate — recurring lifecycle-script-failed pattern`. Include the timestamps of all prior occurrences and the discriminating operator actions appropriate for that category (vendor-exclusion request for hardware; LCS bug for lifecycle; capacity replacement / pool change for capacity). |
| 8 | `replacements_24h_total ≥ 5` — five or more replacements anywhere in the cluster within 24 hours | **Escalate — fleet-wide instability**: the rate of node churn is abnormal regardless of individual root causes. |
| 9 | `replacements_7d_by_group[<ig>] ≥ 5` — five or more replacements on the same InstanceGroup in 7 days | **Escalate — instance-group instability**: the affected IG (which may be a specific SKU or topology placement) is failing more often than the rest of the cluster. |
| 10 | Exactly one replacement attempt in flight, started within the last 30 minutes, no prior failure in the chain | **Monitor — first attempt** (next re-check in 30 min via scheduled audit) |
| 11 | Multiple replacement attempts in the chain, total elapsed since the first failure ≤ 90 minutes, the most recent attempt is *Running* or *Started* (not yet failed) | **Monitor — elevated** (retry in progress, watch closely) |
| 12 | Multiple replacement attempts, total elapsed > 90 minutes, no successful `Running` transition, AND no new attempt started within the last 30 minutes | **Escalate** — retry chain is stuck |
| 13 | Node was in `Failed` state AND no new replacement attempt has started within the last 30 minutes AND total time in failing chain > 60 minutes | **Escalate** — HyperPod has given up |
| 14 | Instance id from the trigger event is missing from `list-cluster-nodes` AND `list-cluster-events` shows no new attempt for the last 30 minutes AND the most recent attempt failed | **Escalate** — instance vanished, no retry |
| 15 | HMA detection event present but no corresponding `Action:*` / replacement event in the timeline within 10 minutes | **Escalate** — HMA fired without escalating; investigate why (mismatch in node-recovery config, signal didn't classify) |
| 16 | None of the above match | **Monitor — uncategorized** (include the full timeline; flag for review) |

**Rule 2 (`Resolved`) closes the loop on prior `Monitor` verdicts.**
A previous `Monitor` verdict promised a re-check; this rule provides
that re-check via the scheduled audit. The verdict description
should explicitly say "Incident detected at <T0> is now resolved.
Total auto-recovery time: <duration>. No operator action required."
This is the closure email the operator needs.

**Rule 1 (`Suppress — periodic audit, no open incidents`) is the no-op
case.** When the scheduled audit fires on a healthy cluster, emit a
single minimal record acknowledging the audit ran. The email notifier
filters `Suppress` verdicts so no email is sent.

**Rule 3 (`Suppress — periodic audit, evidence is stale`) prevents
duplicate-Escalate spam.** The 7-day `list-cluster-events` window
keeps old fault events visible long after the operator has been
notified once. Without this rule, an audit at T+15 min, T+30 min,
T+45 min, ... would each fire the same Escalate verdict against
the same stale evidence — up to ~672 duplicate emails over 7 days
for a single past event burst.

The rule has two protection layers:

1. **Signature-set comparison** (precise): Suppress only when
   `current_signature_set == prior_signature_set`. A new
   `(category, key, IG)` signature — a new category (e.g.
   `lifecycle-script-failed` arriving while `gpu-xid:74` is stale),
   a new key within an existing category (a different Xid number), a
   signature spreading to a new IG, or any combination — produces a
   different set, **breaks the suppression**, and re-Escalates
   regardless of the time window. This is the answer to "what if a
   new type of issue arrives during the 4h window?" — it's not
   suppressed.

2. **Time-based fallback** (safety net): Suppress requires
   `current_most_recent_event_at == prior_most_recent_event_at` (no
   newer fault event since the previous audit). Even if the
   signature set is unchanged but a fresh event of the same
   signature has arrived, the operator gets the updated verdict.

Combined with the platform's 30-minute title-based dedup (which
sees the signature set in the verdict title), the staleness logic
covers both short-window noise and long-window stale-replay noise.

**Recurring-pattern verdicts (7–9) are `Escalate` even when the
individual incident is auto-recovering correctly.** The reasoning is
in your operational goals: HyperPod's resiliency repairs the symptom,
but a 3× recurrence of a categorized fault on the same IG is an
underlying cause (vendor / capacity pool for `gpu-xid`, code bug for
`lifecycle-script-failed`, pool exhaustion for `capacity-insufficient`,
etc.) that auto-recovery can't fix. The verdict explanation should
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

1. **First `symptom`** — titled
   `Triage verdict: <verdict-name> :: <signature-set>` where
   `<verdict-name>` is one of `Suppress`, `Monitor — first attempt`,
   `Monitor — elevated`, `Monitor — uncategorized`, `Resolved — auto-recovery succeeded`,
   or `Escalate — <reason>`. **The `<signature-set>` suffix is
   required for any verdict that names specific fault evidence**
   (all Escalate / Monitor / Resolved variants) — it's a stable,
   sorted-and-deduplicated string representation of the
   `(InstanceGroup, Xid-signature)` pairs that drove the verdict,
   formatted as `(ig1:xid_a, ig1:xid_b, ig2:xid_a, ...)`. Examples:
   - `Triage verdict: Escalate — recurring gpu-xid pattern :: (worker2:gpu-xid:74)`
   - `Triage verdict: Escalate — fleet-wide instability :: (worker2:gpu-xid:74, worker3:gpu-xid:79)`
   - `Triage verdict: Escalate — recurring lifecycle-script-failed pattern :: (worker3:lifecycle-script-failed:)`
   - `Triage verdict: Escalate — recurring capacity-insufficient pattern :: (worker2:capacity-insufficient:ml.g6.4xlarge)`
   - `Triage verdict: Monitor — first attempt :: (worker2:gpu-xid:74)`
   - `Triage verdict: Suppress — periodic audit, evidence is stale :: (worker2:gpu-xid:74)`
   - Mixed-category set: `Triage verdict: Escalate — fleet-wide instability :: (worker2:gpu-xid:74, worker2:lifecycle-script-failed:, worker3:efa-health-check:)`
   - `Triage verdict: Suppress — periodic audit, no open incidents` (no suffix when there's no signature set)

   **Purpose**: the DevOps Agent platform's automatic task-dedup uses
   title equality within a ~30 minute window. Encoding the signature
   set in the title means a NEW signature (a new Xid type on the same
   IG, or the same Xid spreading to a new IG) produces a different
   title and the platform does NOT dedup it — the new investigation
   runs. Conversely, identical signature sets produce identical titles
   and platform dedup quietly absorbs the duplicate audit.

   The description is the prose justification in the shape:

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

   **Always emit an `investigation_gap` when Phase 2b produces
   `category="unclassified"` signatures.** The gap's title should
   be `Unclassified fault signatures observed — skill category
   table needs extension`, and the description should list each
   unclassified event with its full description and timestamp.
   This is how the skill self-reports gaps in its own
   categorization rules and asks the operator to extend the table
   in Phase 2b.

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
description, prefix with one of `[direct]` (observed via API/log
output the agent itself ran), `[proxy]` (inferred from HMA
classification or a correlated source), or `[unverified]` (would need
on-node SSM or AWS-internal data the agent can't reach). This
replaces the separate "Confidence" section.

**`[direct]` requires direct observation, not inference.** A claim
like "all three replacements landed on the same physical host" is
**not** `[direct]` even when three identical fault signatures are
observed — the customer surface (NodeId, InstanceId, ENI, K8s node
name) does not expose physical hardware identity. Such claims are
`[unverified]` at best. Mislabeling inference as `[direct]` is a
serious failure mode because operators trust the annotation to mean
"the agent saw this in the data."

**Hypothesis discipline for recurring-pattern verdicts
(rules 7–9).** When the verdict is one of `Escalate — recurring
hardware fault pattern`, `Escalate — fleet-wide instability`, or
`Escalate — instance-group instability`, the verdict description
MUST enumerate at least **two** competing hypotheses for the root
cause, each labeled `[unverified]` or `[proxy]`, and each paired with
a discriminating operator action. Do not commit to a single root
cause without `[direct]` evidence. The required hypothesis classes
are:

1. **Software / workload** — the workload running on the IG triggers
   the fault on whatever GPU it lands on (NCCL pattern, driver / CUDA
   version, application code path). Discriminator: change the
   workload, or move the IG to a different node and see if the fault
   follows.
2. **Infrastructure path** — an EFA fabric path, leaf switch, or
   shared network resource surfaces as GPU-level errors on workloads
   that hit it. Discriminator: move the IG to a different subnet / AZ.
3. **Statistical hardware** — a bad batch of the same SKU is over-
   represented in the capacity pool. Discriminator: open an AWS
   Support case with the fault signature requesting hardware
   exclusion, or wait + retry later from a different time/pool.

The verdict should NOT include "every replacement is landing on the
same physical hardware" as a stated cause — that's the explanation
**operators are conditioned to expect from on-prem clusters**, but
on HyperPod the EC2 instance is owned by the service account, the
underlying physical host is not exposed on the customer surface, and
EC2 placement is non-deterministic per replacement. Read the
"Recurring fault signature does NOT prove physical-host affinity"
section in [references/hyperpod-mental-model.md](references/hyperpod-mental-model.md)
before authoring this part of the verdict.

**The GPU UUID check is the only way to confirm or refute
physical-host affinity, and it requires SSM (operator-only).** The
verdict's "Recommended actions" section MUST include this check as
an explicit operator step whenever a recurring-pattern verdict is
emitted (rules 7–9). The wording should be:

```
N. Verify or refute "same physical GPU" by capturing GPU UUIDs.
   The agent cannot run this check (requires SSM, which is outside
   the DevOps Agent permission guardrail). For each affected
   instance ID, run:

       aws ssm start-session \
         --target sagemaker-cluster:<cluster-id>_<group>-<instance-id> \
         --document-name AWS-StartNonInteractiveCommand \
         --parameters '{"command":["nvidia-smi -L"]}'

   Compare the UUID strings across the affected instances. If they
   match, the same physical GPU is being recycled — that elevates
   the "statistical hardware" hypothesis to [direct] evidence and
   strengthens the case for an AWS Support exclusion request. If
   they differ, "same physical hardware" is RULED OUT and the
   investigation should pivot to the software/workload and
   infrastructure-path hypotheses instead.
```

Replace `<cluster-id>`, `<group>`, `<instance-id>` with the actual
values from the affected instances in the timeline. List each
instance separately so the operator can run the commands in parallel.

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
