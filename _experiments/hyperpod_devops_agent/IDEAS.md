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


## We should test real repeated lifecycle script errors

repeated lifecycle script errors is one of typical issues we should notify.
Let's modify the lifecycle script so that it fails, then replace multiple instances. Instance replacements should fail and keep retrying. Check what happens. Especially want to confirm the DevOps Agent can understand why Lifecycle script is failing by accessing CloudWatch Logs.


## String truncation logics in the Lambda function

Review string truncation logics in the Lambda function and make sure they are consistent


## Incident title of periodic audit


Got "HyperPod periodic audit: k8-1" as the incident title of periodic audit.
Incidents triggered by EventBridge events have better name including error message, but periodic audit ones don't. Can we improve it?



## Notification integration

Want to setup email and slack notification, and see end-to-end experience
