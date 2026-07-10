# Design: Lambda-side audit detection (fire webhook only on real issues)

Status: **proposed** (design only, not implemented). 2026-07-10.

## Problem

Today the periodic-audit Lambda **always** POSTs a synthetic "periodic audit"
event to the webhook every 15 minutes. Each POST creates a DevOps Agent
INVESTIGATION task; the `hyperpod-incident-rca` skill inspects the cluster and,
on a healthy cluster, lands on `Suppress` (the email notifier then drops it).

Observed cost on a healthy cluster (k8-1, overnight 2026-07-10): audits alternate
**Completed (full RCA → Suppress)** and **Skipped (triage concurrency rule)**,
roughly one full RCA every ~30 min. So a healthy cluster still burns ~2
investigations/hour for zero operator value.

Why triage can't just LINK the healthy audits away: to decide "nothing changed
since the last audit," the triage agent would need to inspect current cluster
state and compare it to the prior audit — which *is* the RCA work. The v0.7.0
triage skill was deliberately simplified to concise declarative rules (that's
what made it reliable), so it no longer computes/stores a cluster signature to
compare against. Net: once the concurrency window passes, PROCEED is the only
decision triage can reach, and a full RCA runs.

## Idea (from IDEAS.md)

> DevOps Agent is designed for event-driven real issues, not polling. Detect the
> Kubernetes resource issue **in the Lambda** and call the webhook **only when
> there is a real issue.**

This inverts the model from **fire-always + suppress-in-RCA** to
**detect-first + fire-only-on-signal**:

- Healthy cluster → Lambda finds nothing → **no webhook → zero investigations, zero cost, zero triage churn.**
- Real problem appears → Lambda fires the webhook → RCA runs on a genuine signal.
- Triage's remaining job shrinks to deduping *real* incidents (the cross-fault
  separation rule), which is what skills are good at.

## What the Lambda checks (reuse existing thresholds)

The audit Lambda already receives these as env vars (today it only forwards them
into the payload for the skill). Move the *evaluation* into the Lambda:

| Signal | Source | Fire when | Threshold param (existing) |
|---|---|---|---|
| **CrashLoopBackOff** | `kubectl get pods -A -o json` | any pod in CrashLoopBackOff longer than the threshold | `CrashLoopHoursThreshold` (default 4) |
| **NotReady nodes** | `kubectl get nodes -o json` | ≥ percent of nodes NotReady for ≥ duration | `NotReadyNodePercentThreshold` (10), `NotReadyDurationMinutes` (15) |
| **Open fault chains** | `sagemaker list-cluster-events` (last 4h, Error/Warn, excluding scale-in-progress "lost orchestration-ready" noise) | any unresolved fault event present | — |

Namespace handling reuses `IgnoreNamespaces` / `SystemNamespaces` exactly as the
skill does today (skip ignored namespaces; tag system vs customer for routing).

**Decision:** if **any** signal trips → build the webhook payload (as today) and
POST, including a structured `data.metadata.detectedIssues` block describing what
tripped, so the RCA skill starts with the finding instead of rediscovering it.
If **nothing** trips → log "healthy, no webhook" and return 200 without POSTing.

## What changes in the stack

1. **Audit Lambda needs cluster read access** (it has none today — only Secrets
   Manager + logs):
   - **EKS (kubectl):** add a **dedicated** `AWS::EKS::AccessEntry` whose
     `PrincipalArn` is the *audit Lambda's execution role*, with a read-only
     access policy (`AmazonEKSViewPolicy`, **cluster scope / all namespaces** per
     decision below). Gate on `IsEksCluster` like the existing entry. Slurm
     clusters skip this and rely on `list-cluster-events` only.

     **Why not reuse the existing access entry?** (asked 2026-07-10) Two hard
     reasons:
     1. An access entry is keyed to exactly one IAM principal ARN. The existing
        one's principal is the **Agent Space role** — it authorizes *that*
        identity in the cluster and grants the Lambda nothing. For the Lambda to
        call the K8s API, the cluster must recognize *the Lambda's own execution
        role*, which requires its own entry.
     2. The Lambda can't assume the Agent Space role anyway: that role trusts
        only `aidevops.amazonaws.com` (scoped to `agentspace/*`), not
        `lambda.amazonaws.com`. The Lambda runs as its own execution role and
        calls the K8s API directly. Adding Lambda to that role's trust + an
        `sts:AssumeRole` hop is more moving parts and broadens the blast radius
        of a role the DevOps Agent guardrail governs. A separate, independently
        revocable entry for the Lambda is cleaner.
   - **Scope decision:** start with **cluster-scope, all namespaces, read-only**
     (`AmazonEKSViewPolicy`). Node reads (NotReady check) are inherently
     cluster-scoped, so namespace-scoping wouldn't cover them anyway. Tighten
     later if needed.
   - **SageMaker:** add `sagemaker:ListClusterEvents` + `sagemaker:DescribeCluster`
     to the audit Lambda role (scope to the cluster ARN).
   - **Calling the K8s API — no `kubernetes` client, no Lambda layer, no
     packaging step (decision 2026-07-10).** We only need two read calls (list
     pods, list nodes), so hit the EKS API server directly with **stdlib
     `urllib` + a SigV4 bearer token generated via boto3** (already in the
     runtime). The token is the standard
     `k8s-aws-v1.<base64 presigned STS GetCallerIdentity URL>` scheme that
     `aws eks get-token` / aws-iam-authenticator produce (~15 lines). The
     cluster API endpoint + base64 CA cert come from `eks describe-cluster`
     (write the CA to `/tmp` and pass to `urllib` as the TLS ca-bundle).
     - If a future need calls for the full `kubernetes` client, package it as an
       **S3 zip** the same way the skill uploader bundles boto3 (`pip install
       --target` → zip → S3 → `Code.S3Bucket`). Prefer this over a formal Lambda
       layer — no extra layer resource to version/manage. But for pods+nodes the
       stdlib approach above is simpler and is the recommended path.
2. **Lambda code:** add the three checks + the fire/no-fire decision. Keep the
   HMAC-POST path unchanged; only its invocation becomes conditional.
3. **Payload:** add `data.metadata.detectedIssues` (list of `{type, resource,
   detail, tag}`). The RCA skill's audit-mode branch reads it as the starting
   point rather than re-discovering (it can still verify).
4. **Skill impact:** the RCA skill's audit-mode discovery becomes *confirmation*
   rather than *discovery*. The triage concurrency rule still applies. The
   "audit signature / stale-evidence" machinery is no longer needed for cost
   control (the Lambda gates volume now) — can be simplified later.
5. **New param (optional):** `AuditDetectionMode` = `lambda` (new, gated
   detection) | `always-fire` (current behavior) so the change is reversible and
   testable side-by-side.

## Tradeoffs

- **Pro:** healthy clusters cost ~0; investigations correspond to real signals;
  removes the "triage can't tell if anything changed" problem entirely; less
  email/triage churn.
- **Con:** duplicates a slice of detection logic in the Lambda that also lives in
  the RCA skill (mitigated by passing `detectedIssues` so the skill trusts the
  Lambda's finding). Adds EKS read access + a kubectl/EKS client dependency to
  the Lambda. Loses the "agent looks at the cluster every 15 min regardless"
  property — acceptable, since a healthy cluster produced only Suppress anyway.
- **Slurm:** detection reduces to `list-cluster-events` only (no kubectl); still
  a net win vs. always-fire.

## Decisions (2026-07-10)

- **K8s API access:** stdlib `urllib` + boto3-generated SigV4 token (no
  `kubernetes` client, no layer). See stack change #1.
- **EKS access policy scope:** cluster-wide, all namespaces, read-only
  (`AmazonEKSViewPolicy`). See stack change #1.
- **Heartbeat: keep a daily audit.** Even when the cluster is healthy and no
  issue trips, fire the webhook **once per day** so operators see the pipeline is
  alive (and get a periodic "healthy" confirmation). Implementation: the Lambda
  fires if *either* an issue trips *or* it's the day's designated heartbeat run.
  The heartbeat run carries a flag (e.g. `data.metadata.heartbeat: true`) so the
  RCA skill / email notifier can treat it as an informational "all clear" rather
  than an incident. Cost: 1 healthy RCA/day instead of ~48.

## Open questions

- Exact form of the daily-heartbeat trigger: a second EventBridge Scheduler at
  `rate(1 day)` that always fires, vs. the 15-min Lambda self-detecting "first
  run after 00:00 UTC." A separate daily schedule is simpler and unambiguous;
  lean that way unless there's a reason to keep it in one Lambda path.
- Heartbeat email policy: does the operator want the daily "all clear" email, or
  only the liveness signal in the console/logs? (Affects the email notifier's
  filter for `heartbeat: true`.)
