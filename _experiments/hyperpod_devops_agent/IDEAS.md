# Ideas + Questions

Scratchpad. Just write. Title + a couple of lines + any relevant IDs.

## Bridge misses `EventMetadata.Cluster.FailureMessage` [done]

Bridge only reads `EventMetadata.Instance.FailureMessage`. Cluster-level events put it under `EventMetadata.Cluster.FailureMessage`. Fix: walk all subtrees under `EventMetadata`.

Investigation: `e281cd02-2df7-4245-8249-5860f4dd7e4a`
EventId: `127b07cf-9f00-4bdf-801e-11481419c562`

Fixed in `webhook_bridge/lambda_function.py`. Verified: re-invoking with the same EventId now produces title `"HyperPod cluster / Request to service failed. If failure persists after retry, contact customer support."` instead of falling back to the generic Description text.


## Getting Warning "1 node(s) lost orchestration-ready status" when scaling down [done]

I manually initiated scaling down by calling UpdateCluster API. Make sure the DevOps Agent recognize it and triage correctly.

Investigation: `e281cd02-2df7-4245-8249-5860f4dd7e4a`

**Observed on scale-down worker4 8→0 at 2026-07-01T02:05Z**: 3 primary tasks created (not linked). All had identical titles (`HyperPod cluster / Request to service failed...`) but distinct descriptions:
- `3 node(s) lost orchestration-ready status. Current: 10/5 ...` → task `b79b658b`
- `4 node(s) lost orchestration-ready status. Current: 6/5 ...` → task `f6041670`
- `1 node(s) lost orchestration-ready status. Current: 5/5 ...` → task `53fced6b`

Root cause: our concat-signature `<ig>:<Description + FailureMessage>` treats the variable node counts as distinct. Same-operation events don't LINK.

**Fix chosen**: SKIP at triage stage when Description contains `"lost orchestration-ready status"` AND `describe-cluster` shows any InstanceGroup with `CurrentCount != TargetCount`. Signature-normalization (options 1-3 above) is not needed — these events shouldn't produce investigations at all.

**Shipped**:
- Triage skill v0.3.0 rule 3 (new): SKIP with reason `"Cluster scale-in-progress: <IG> is <cur>/<target>. 'lost orchestration-ready' events during scaling operations are progress updates, not incidents."`
- Mental-model doc new section "Scale-in-progress emits spurious `Warn` events with misleading FailureMessage" — documents the ambient FailureMessage `"Request to service failed..."` HyperPod attaches to these events, so future skills don't misread it as a fault signal.

**Verified 2026-07-01T03:20Z on scale-down worker4 3→0** (immediately after the LCS-failure test):
- One Warn "lost orchestration-ready" event fired at 03:20:31Z — `EventId=8a90a42e-47cb-44ed-ba5e-ae7196d025ea`, Description `"1 node(s) lost orchestration-ready status. Current: 5/5 orchestration-ready across 4 instance group(s)."`, FailureMessage `"Request to service failed..."`.
- Bridge forwarded it (Warn, not filtered), task `0ee22f60-5892-46ed-b47a-0d8283b96acc` created at 03:20:49Z.
- Triage set **`status=SKIPPED`** with reason: *"[hyperpod-incident-triage] rule 3: Cluster scale-in-progress or node replacement. 'lost orchestration-ready status' event with FailureMessage 'Request to service failed' during active worker4 lifecycle failures and deletion operations. Status already recovered (Current: 5/5 orchestration-ready). This is a transient progress update, not an incident requiring investigation."*
- Notable: the event fired *after* the cluster had already returned to 5/5, but triage still reasoned about the recently-completed replacement activity and SKIPPED — smarter than a hard `CurrentCount != TargetCount` gate. No email, no RCA billed.
- Related follow-up: `"deletion request received"` events during scale-down (task `f512a354`) — see [Triage rule for "deletion request was received" during scale-down](#triage-rule-for-deletion-request-was-received-during-scale-down) below.

**Re-verified 2026-07-07T23:40Z on scale-down worker2 2→0**: the v0.3.0 triage rule 3 (describe-cluster check) failed to fire — the describe-cluster call sees Cur==Tgt by the time it executes (race). The first event `ec19d171` PROCEEDed as a new primary, the second `ffad8da7` LINKED by the default AI correlator (not our rule).

**Revised approach (v0.4.0)**: moved filtering upstream to the bridge Lambda — events with Description containing `"lost orchestration-ready status"` are now dropped before they reach the webhook. The RCA skill also excludes them from `signature_count_7d` so they don't trigger rule 6 Escalate verdicts during audit walks. Triage rule 3 removed (superseded). Asking engineering to fix the underlying spurious-event issue.


## We should test real repeated lifecycle script errors [done]

repeated lifecycle script errors is one of typical issues we should notify.
Let's modify the lifecycle script so that it fails, then replace multiple instances. Instance replacements should fail and keep retrying. Check what happens. Especially want to confirm the DevOps Agent can understand why Lifecycle script is failing by accessing CloudWatch Logs.

**Test executed 2026-07-01T02:51Z on `k8-1/worker4`.** Injected a missing-binary fault (`hyperpod-fault-injection-tool`) into `on_create.sh`, scaled `worker4` 0→3, watched for ~20 min, then restored.

Observations:
- **CloudWatch Logs path works end-to-end.** RCA execution `exe-ops1-2a485bf3-aefb-4b9d-ac06-a60975994b07` (primary task `431f3c82`) spawned a `lifecycle-logs` subagent that read `/aws/sagemaker/Clusters/k8-1/lw12e0dn1hhd::LifecycleConfig/worker4/i-*`, extracted the `[fault-injection] devops-agent-test: invoking missing binary hyperpod-fault-injection-tool` line, and named it as the root cause within ~3 min of the first `Warn` event. This confirms the guardrail-safe HMA→CloudWatch proxy path is sufficient for LCS failures.
- **CloudTrail correlation was a free bonus.** The agent also enumerated the prior 4 `UpdateCluster` calls on `worker4` from earlier debugging cycles and correctly identified the 02:51:16 CLI-issued scale-up as *this* incident's trigger, distinguishing it by user agent (`ClaudeCode-BH` vs. earlier Boto3 calls).
- **Triage-skill signature dedup held under load.** 3 initial failures + 3 retry-wave failures = 12 raw events → 1 primary `IN_PROGRESS`/`COMPLETED` + 11 `LINKED`. No duplicate investigations spun up during the retry wave (03:04Z). Cost: exactly 1 investigation for a 6-instance repeated LCS storm.
- **Retry-wave detection is *implicit*, not explicit.** The agent recognized the retry pattern in a follow-up chat turn ("second retry wave (03:04:43–03:05:06 UTC), confirming HyperPod's Continuous provisioning mode is automatically re-attempting and failing identically"), but the primary investigation completed *before* the retries arrived, so its final report treats it as a single-shot incident. Recurrence rules 6-8 in the RCA skill fire on `list-cluster-events` history (Xid/replacement counts), not on LCS repetitions — a stuck-LCS retry loop wouldn't cross those thresholds. Possible follow-up: add an LCS-repetition signature (e.g. count of `LifecycleConfig/<ig>/*` streams in the last N min matching an "on_create failed" pattern) to the triage or RCA skill so the verdict itself reflects "repeated LCS failure, retries are also failing → Escalate".
- **Periodic audit properly linked.** The 15-min audit event at 03:04:42Z (task `a4ed3938`) landed inside the LCS-failure window and was auto-LINKED to the primary — the 5-layer dedup architecture behaved as documented in README.md.
- **Investigation gap surfaced.** The RCA correctly flagged `s3-script-content-inaccessible` as a gap: `DevOpsAgentRole-AgentSpace` lacks `s3:GetObject`/`s3:ListBucket` on the LCS bucket, so the agent couldn't read the current `on_create.sh` to confirm the injection or find *when* it was added. Adding `s3:GetObject` on the LCS bucket (via the guardrail's opt-in allowlist) would close this.

Backup + fault-injected LCS retained locally at `/tmp/lcs_test/backup_20260701T024847Z/` and `/tmp/lcs_test/on_create_broken.sh` (not checked in) for future re-runs.


## Triage rule for "deletion request was received" during scale-down

Task `f512a354-175e-490f-b18e-b8f6eebf4116` (2026-07-01T03:12:55Z, worker4) PROCEEDed through triage and reached RCA — final symptom title `"Triage verdict: Escalate — recurring fault pattern"`. RCA correctly identified the deletion-during-provisioning as benign (`"expected HyperPod behavior when a scale-down overlaps with active provisioning"`), but rolled it into the escalate verdict alongside the still-open LCS loop. A full RCA is wasted work when the FailureMessage is caused by an operator-initiated scale-down that overlaps in-flight provisioning.

**Proposed triage rule**: SKIP when `FailureMessage` contains `"instance provisioning could not be complete because a deletion request was received"` AND `describe-cluster` shows the same instance group with `ActiveOperations.Scaling` present and `TargetCount < CurrentCount` (or the failing instance's `LaunchTime` is within N seconds of a CloudTrail `UpdateCluster` call that reduced `TargetCount`). Same shape as rule 3 (scale-in-progress) but for the deletion-during-provisioning surface.

Edge case to preserve: if `ActiveOperations.Scaling` is absent by the time the event fires (scale-down already completed), the correlation window against CloudTrail is what saves it — don't rely only on the live describe-cluster snapshot.


## `s3:GetObject` on the LCS bucket to prevent RCA hallucination [done]

Task `f512a354` RCA fabricated a plausible-but-wrong root cause (`configure-efa-fsx-lustre-client.service failing on ml.g5.8xlarge, a non-EFA type`) because `DevOpsAgentRole-AgentSpace` couldn't read `s3://sagemaker-k8-1-1bd2626f-bucket/on_create.sh`. The actual LCS at the time was our missing-binary fault injection. The agent tagged the finding `[proxy]` and listed `lifecycle-script-source-code` as an `investigation_gap`, but still produced a confident-looking EFA/FSx hypothesis in the final report.

**Shipped**: `foundation/template.yaml` now grants `s3:GetObject` + `s3:ListBucket` on `arn:aws:s3:::sagemaker-*-bucket` (and `/*`) to `DevOpsAgentRole-AgentSpace` via a new `AllowLcsBucketRead` inline policy. Scope is parameterizable through the `LcsBucketArnPattern` CFN parameter — override to a specific bucket ARN for tighter scoping, or set to `""` to skip the grant entirely. Both actions are in the guardrail's opt-in allowlist so the grant actually takes effect.

Wildcard-bucket scope was chosen over the narrower `.../on_create*` or per-cluster discovery approaches:
- HyperPod-created LCS buckets follow the `sagemaker-<cluster>-<hash>-bucket` pattern, so the wildcard cleanly targets them without picking up unrelated buckets.
- Users often add other scripts referenced by `on_create.sh` (helper scripts, configs). Path-scoping to `on_create*` alone would re-introduce the "can't read the referenced file" gap.
- Per-cluster discovery would require a bootstrap Lambda and re-deploy on new-cluster addition. Not worth the ergonomics tax.

Next verification: re-run the LCS-failure test (backup + fault-injected LCS at `/tmp/lcs_test/`) and confirm the RCA cites the actual script content instead of the EFA hypothesis.


## Notification integration [done — email]

Set up email and see end-to-end experience. Slack is still paused on workspace 3P approval.

**Shipped (2026-07-08)**: `email_notifier/` CloudFormation stack — EventBridge rule on `aws.aidevops` `Investigation Completed` (Created/Updated/Linked events are ignored so we send exactly one email per lifecycle) → Lambda → SES `SendEmail` with HTML body.

Filter chain in `email_notifier/lambda_function.py`:
1. Detail-type allowlist (default: `Investigation Completed` only).
2. **Per-execution S3 dedup marker** — HeadObject against `s3://hyperpod-devops-agent-email-markers-<account>-<region>/emailed/<execution_id>` before doing any DevOps Agent API calls. Marker is written *after* a successful `ses:SendEmail`. Prevents duplicate emails when DevOps Agent re-emits `Investigation Completed` for the same execution (which it does — observed empirically). Marker bucket has a 30-day lifecycle rule; adjustable via `MarkerExpirationDays` CFN parameter.
3. Suppress-verdict detection reading the journal directly (checks `Triage verdict: Suppress` prefix on any symptom title, plus a `Verdict: Suppress` regex fallback on the first symptom's description). No longer relies on `SKIP_VERDICT_PREFIXES` env var — that was brittle across skill drift.
4. No-actionable-content skip — investigations with zero findings and no verdict symptom are dropped.
5. `FORCE_SEND=true` CFN parameter bypasses every filter for debugging.

Body composition rewrite: the notifier now pulls **full journal records via `list_journal_records`** and composes HTML from symptoms + findings + investigation_gaps rather than parsing a single verdict-title string. Resilient to future RCA-skill drift as long as *some* record identifies a root cause. Subject line still uses the verdict headline when present.

Console URL template updated to the actual working shape: `.../aidevops/home?region=%region%#/agentspaces/%agent_space_id%/investigations/%task_id%` (previous `/investigations/%investigation_id%` was 404).


## Verdict-title fragility → made the FIRST symptom the verdict symptom [done]

RCA runs were occasionally emitting a descriptive first symptom title (e.g. `"worker1 lifecycle script execution failures across multiple nodes on k8-1"`) instead of the `"Triage verdict: ..."`-prefixed one. Downstream automation (email subject headline, dedup title-matching) then went blind because it keys off the verdict-title prefix.

**Fix**: added a `CRITICAL: the FIRST symptom is the verdict symptom` section + four few-shot examples (Escalate recurring, Escalate coordinated LCS, Monitor first-attempt, Suppress audit) + an anti-example, all in [skills/hyperpod-incident-rca/SKILL.md](skills/hyperpod-incident-rca/SKILL.md#L425). Descriptive titles are now for the *second* and later symptom records. The email notifier's headline picker still falls back to the first-symptom title / task title if no verdict-prefixed symptom exists, so a drift regression degrades gracefully.


## Kubernetes-state checks in periodic audit — CrashLoopBackOff + NotReady nodes [done]

The audit-mode RCA already had `kubectl` read access via the EKS access entry but only inspected HyperPod-level state. Extending to Pod / Node checks catches a class of incidents HyperPod itself doesn't emit events for.

**Shipped**:
- Two Phase 3d rules in the RCA skill ([skills/hyperpod-incident-rca/SKILL.md](skills/hyperpod-incident-rca/SKILL.md#L343)): CrashLoopBackOff duration and NotReady node percentage. Both are audit-mode-only + EKS-only.
- Six new CFN parameters on the periodic-audit stack: `K8sChecksEnabled`, `CrashLoopHoursThreshold` (default 4h), `NotReadyNodePercentThreshold` (default 10%), `NotReadyDurationMinutes` (default 15 min), `IgnoreNamespaces`, `SystemNamespaces`. Env-var overrides on `make deploy-periodic-audit`.
- Namespace handling uses **two plain lists** (`IgnoreNamespaces` + `SystemNamespaces`), pre-parsed and validated for non-overlap in the audit Lambda. The skill executes classification via set-membership lookups — no DSL, no regex, no wildcards. Rationale: LLMs handle content comparison well but parse-and-execute-a-mini-language less reliably; the earlier hard-coded-enum version of the RCA skill was replaced by signature-string concatenation for exactly this reason, and the same principle applies here.
- Overlap between `IgnoreNamespaces` and `SystemNamespaces` fails the audit invocation at cold start with an explicit error, so ambiguous-membership pods can't reach runtime.
- Trigger payload carries `data.metadata.k8sChecks` block with resolved thresholds + lists. Skill reads from the block, no hardcoded values.
- Interaction with existing rules: Phase 3d runs after the main fault-chain classification and emits its own independent verdicts. The rule-1 `Suppress` for a healthy cluster is skipped if Phase 3d produces any verdict.

Next verification: real-cluster smoke test — deploy a Pod that crashloops, wait for the audit cycle, confirm an Escalate email arrives with the workload-class tag. Currently untested end-to-end.


## Weekly digest for GPU-utilization + FinOps signals

Absolute-utilization thresholds (e.g. "average <80% over 7d") don't work as incident triggers — real workloads on well-tuned code hit 60–80% MFU, exploration/notebook work hits 20–40%, so an 80% floor pages ops for every researcher iterating on a training script. This is a **FinOps / capacity-planning signal**, not an SRE-page.

Better shape: a separate **weekly digest** email (different recipients, different tone) surfacing:
- Per-IG average GPU utilization over the trailing 7d.
- Sudden utilization drop on a previously-hot IG (e.g. "worker4 was 70%+ for 6 days, now <10% for 12h and no scale-down") — that delta signal *is* actionable and could go straight into the incident channel because it points at a stuck job or GPU fault.
- Replacement counts by IG over 7d (already computed by RCA rule 8, currently only surfaced when it crosses the Escalate threshold).
- Optional: cost estimate delta week-over-week.

Prerequisites:
- **GPU metrics source.** Container Insights + DCGM exporter aren't on by default on HyperPod EKS. Verify what's in place before designing around it. Alternatively CloudWatch's built-in EC2 GPU metrics (limited) or Amazon Managed Prometheus (see next section).
- Delivery: a new EventBridge Scheduler rule at `cron(0 15 ? * MON *)` → dedicated Lambda → SES email. Skips the DevOps Agent entirely — no investigation billed, just a report. Alternatively, use DevOps Agent's native "Agents" (custom scheduled agents for weekly ops reports) if we want it inside the same product.
- Threshold-based Escalate can still live in the audit-mode skill for the specific delta case; the digest handles the ambient reporting.


## Amazon Managed Prometheus as a data source — same guardrail shape as SSM

HyperPod has an official AMP integration (kube-prometheus stack ships DCGM exporter, node-exporter, kube-state-metrics into an AMP workspace). Would be a natural data source for GPU utilization, ECC counters, NVLink stats, XID counts, EFA fabric health — the exact HMA/on-node signals the guardrail otherwise blocks us from seeing.

**Guardrail check (UG p. 358 — verified 2026-07-08)**: `AIDevOpsAgentAccessPolicy` includes `aps:Describe*` and `aps:List*` only. The data-read APIs — `aps:QueryMetrics`, `aps:GetLabels`, `aps:GetSeries`, `aps:GetMetricMetadata` — are **not** in the guardrail allowlist. Same shape as `ssm:StartSession`: adding them to the customer role has no effect because the session policy strips them.

So the agent can:
- Enumerate AMP workspaces via `aps:ListWorkspaces` / `aps:DescribeWorkspace`.
- See that HyperPod is publishing to workspace `ws-<id>`.
- **Not** query any time-series data.

Two paths forward:
1. **Ask AWS to add AMP query actions to the guardrail allowlist** (`aps:QueryMetrics`, `aps:GetLabels`, `aps:GetSeries`, `aps:GetMetricMetadata`). This is a much narrower and more defensible ask than the SSM one — read-only, scoped by workspace ARN, no on-node blast radius, no interactive shell. Bundle it with the SSM feedback item.
2. **AMP → CloudWatch bridge.** Amazon Managed Grafana / AMP alerts can already fan out to SNS. Route them through EventBridge → our webhook bridge → investigation, same shape as the SageMaker `Cluster Event` stream. Doesn't get us ad-hoc query capability during investigations, but does unlock threshold-based triggers on Prometheus metrics (per-Xid-code counts, per-GPU thermal alerts, EFA error rate) that the SageMaker EventBridge stream doesn't expose. The RCA skill would still be reasoning from HMA CloudWatch streams for post-trigger context, not from the raw Prometheus data.

Path 2 is buildable today and complements Goal 2's recurrence detection with sharper trigger signals. Path 1 is the durable fix. File the guardrail-expansion feedback either way.


## Can DevOps Agent access CloudWatch Metrics?

We could use it to monitor hardware resource utilization, etc.


## Periodic Auditing improvement

DevOps Agent is not good at periodic auditing. It is designed to handle real issues event-driven.

Can we detect Kubernetes resource issue not in DevOps Agent but in Lambda function side? Then call webhook only when there is a real issue.

**Design written up (2026-07-10):** see
[docs/lambda-side-audit-detection-design.md](docs/lambda-side-audit-detection-design.md).
Confirmed empirically that on a healthy cluster the always-fire model still runs
~2 full RCAs/hour (alternating Completed/Skipped) — triage can't LINK them away
because it has no cheap way to know "nothing changed" without doing the RCA. The
design moves the CrashLoop/NotReady/open-fault detection into the audit Lambda
(reusing the existing threshold params) and POSTs the webhook only when a real
issue trips, so a healthy cluster costs ~0 investigations. Main new requirement:
the audit Lambda needs read-only EKS access (it has none today).


## We are not using "Agent instructions".

**Finding (2026-07-10): Agent Instructions are likely the more reliable home for
our triage rules than a Skill — but there's no API/CFN path yet, so parked.**

Difference (from the [UG](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent-agent-instructions.html)):

| | Skill (what we use now) | Agent Instructions (AGENTS.md) |
|---|---|---|
| Injection | **On demand** — the agent decides via skill-description matching; it *can skip* the content | **Always** — unconditionally injected into the system prompt every session; the agent cannot skip it |
| Triage scoping | `agent_types: ["INCIDENT_TRIAGE"]` | Scoped to the **Incident triage** managed agent specifically |
| Format | Markdown or ZIP (+ resource files) | Markdown only, no frontmatter, no resources |
| Count | Many per space | Exactly one global + one per managed agent |
| Size | — | 25 KB hard limit; ~120 lines recommended |

**Why this matters for us:** our entire triage saga was about *reliability of
invocation*. A skill fires only if the agent matches its description to the task
(exactly why v0.6.1 silently didn't fire, and why v0.7.0 "works" but still
depends on the agent choosing to apply it). **Incident-triage Agent Instructions
are guaranteed-injected every session** — strictly more reliable for the
"keep different fault types separate / concurrency-skip" rules. Our v0.7.0 skill
is already concise declarative markdown (~50 lines), so it would drop into an
AGENTS.md almost verbatim.

**Why parked, not adopted now:** there is **no `CreateAsset`/CLI/CFN path** for
Agent Instructions (the `CreateAsset` assetType enum is empty; the UG documents
only the Operator Web App Knowledge → Instructions tab: View/Edit/Upload/
Download/Delete). So they'd be a **manual, per-Agent-Space console step**, which
breaks the one-command-deploy goal. Decision: keep the automated v0.7.0 triage
Skill for now; revisit moving the rules to Incident-triage Instructions if/when
AWS exposes a programmatic path. If maximum triage reliability is needed before
then, an operator can paste the v0.7.0 rules into Knowledge → Instructions →
Incident triage manually.

Instructions are also the natural home for **always-on standing guidance** that
isn't task-specific (e.g. "this Agent Space monitors a HyperPod cluster; treat
`sagemaker:cluster` resources as HyperPod, not generic SageMaker") — a separate,
smaller use we could adopt later.




