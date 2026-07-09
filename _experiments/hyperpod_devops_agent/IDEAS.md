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


## `s3:GetObject` on the LCS bucket to prevent RCA hallucination

Task `f512a354` RCA fabricated a plausible-but-wrong root cause (`configure-efa-fsx-lustre-client.service failing on ml.g5.8xlarge, a non-EFA type`) because `DevOpsAgentRole-AgentSpace` can't read `s3://sagemaker-k8-1-1bd2626f-bucket/on_create.sh`. The actual LCS at the time was our missing-binary fault injection. The agent tagged the finding `[proxy]` and listed `lifecycle-script-source-code` as an `investigation_gap`, but still produced a confident-looking EFA/FSx hypothesis in the final report.

**`s3:GetObject` is in the guardrail's opt-in allowlist** (from the AWS DevOps Agent UG). Adding it — scoped to `arn:aws:s3:::sagemaker-<cluster>-*/on_create*.sh` and any other referenced LCS paths — would let the agent read the actual script content instead of guessing.

Scoping options:
- Wildcard per HyperPod-created LCS bucket: `arn:aws:s3:::sagemaker-*-bucket/*` (simple but broad — includes any script/config in that bucket)
- Path-scoped to LCS entrypoints: `arn:aws:s3:::sagemaker-*-bucket/on_create*` + `.../lifecycle*` (narrower; may miss custom scripts)
- Discovered per-cluster at foundation-stack deploy time from `describe-cluster.InstanceGroups[].LifeCycleConfig.SourceS3Uri` (tightest; adds bootstrap dependency)

Would add to `foundation/template.yaml` under `DevOpsAgentRole-AgentSpace` as an inline policy. Verify by re-running the LCS-failure test after the change and confirming the RCA cites the actual script content instead of the EFA hypothesis.


## String truncation logics in the Lambda function

Review string truncation logics in the Lambda function and make sure they are consistent


## Incident title of periodic audit


Got "HyperPod periodic audit: k8-1" as the incident title of periodic audit.
Incidents triggered by EventBridge events have better name including error message, but periodic audit ones don't. Can we improve it?



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


## Should we monitor HMA agent logs as the trigger of incident?


## Should we monitor cluster status in periodic audit?

There may be cases we can/should detect issues not by receiving Events but by periodically checking clusters, for example, number of "Ready" status nodes, number of struggling Pods, etc.

How about other types of notifications, such as existence of new AMI, Helm chart, etc.

