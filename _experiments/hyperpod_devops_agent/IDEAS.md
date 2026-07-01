# Ideas + Questions

Scratchpad. Just write. Title + a couple of lines + any relevant IDs.

## Bridge misses `EventMetadata.Cluster.FailureMessage` [done]

Bridge only reads `EventMetadata.Instance.FailureMessage`. Cluster-level events put it under `EventMetadata.Cluster.FailureMessage`. Fix: walk all subtrees under `EventMetadata`.

Investigation: `e281cd02-2df7-4245-8249-5860f4dd7e4a`
EventId: `127b07cf-9f00-4bdf-801e-11481419c562`

Fixed in `webhook_bridge/lambda_function.py`. Verified: re-invoking with the same EventId now produces title `"HyperPod cluster / Request to service failed. If failure persists after retry, contact customer support."` instead of falling back to the generic Description text.


## Getting Warning "1 node(s) lost orchestration-ready status" when scaling down [in-progress]

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

Waiting on verification: next customer-initiated scale-up or scale-down producing "lost orchestration-ready" Warn events should now SKIP at triage (no investigation, no email).


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


## String truncation logics in the Lambda function

Review string truncation logics in the Lambda function and make sure they are consistent


## Incident title of periodic audit


Got "HyperPod periodic audit: k8-1" as the incident title of periodic audit.
Incidents triggered by EventBridge events have better name including error message, but periodic audit ones don't. Can we improve it?



## Notification integration

Want to setup email and slack notification, and see end-to-end experience


## Should we monitor HMA agent logs as the trigger of incident?


## Should we monitor cluster status in periodic audit?

There may be cases we can/should detect issues not by receiving Events but by periodically checking clusters, for example, number of "Ready" status nodes, number of struggling Pods, etc.

How about other types of notifications, such as existence of new AMI, Helm chart, etc.

