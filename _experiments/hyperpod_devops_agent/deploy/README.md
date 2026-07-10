# Single-template deployment

One CloudFormation stack that deploys the entire HyperPod × AWS DevOps Agent
solution — foundation (IAM roles + Agent Space + AWS-monitor association), EKS
read-only access, the webhook bridge, the periodic audit, the email notifier,
and the two skills. Replaces the four separate stacks + imperative scripts under
the parent directory (those are kept until this path is validated).

## Why two custom resources

Everything is deployed with official resource types **except** two gaps that
CloudFormation cannot express (verified against the Dec 2025 template reference):

1. **eventChannel webhook** — `AWS::DevOpsAgent::Service` has no `eventChannel`
   ServiceType, and `AWS::DevOpsAgent::Association` with an `EventChannel`
   configuration does not expose the generated webhook URL / HMAC secret as a
   `Fn::GetAtt`. → `Custom::WebhookProvisioner` (register/associate + stash the
   secret into Secrets Manager).
2. **Skill assets** — there is no `AWS::DevOpsAgent::Asset` resource type.
   → `Custom::SkillUploader` (create/update/delete skill assets from S3).

The EKS access grant, previously an imperative script, is now the native
`AWS::EKS::AccessEntry` (skipped automatically for Slurm clusters).

## Layout

```
deploy/
  hyperpod_devops_agent.yaml  - the single template (with # *_CODE_PLACEHOLDER markers)
  lambda/
    webhook_bridge.py        \
    periodic_audit.py         > glue Lambdas (unchanged from the old stacks)
    email_notifier.py        /
    cr_webhook_provisioner.py - Custom::WebhookProvisioner handler
    cr_skill_uploader.py      - Custom::SkillUploader handler
  prepare_deployment.py  - embed Lambda code into the template; sync skills to S3
  deploy.sh              - one-command deploy (called by `make deploy`)
  teardown.sh            - delete stack + assets bucket (`make teardown-stack`)
  params.example.json    - copy to params.json and edit
```

`prepare_deployment.py embed` inlines each `lambda/*.py` at its
`# <NAME>_CODE_PLACEHOLDER` marker, producing
`hyperpod_devops_agent.embedded.yaml` (git-ignored build artifact).

## Quick start

```bash
cd _experiments/hyperpod_devops_agent
cp deploy/params.example.json deploy/params.json
# edit deploy/params.json: HyperPodClusterName, EmailSender, EmailRecipients
#   (the SES sender must be verified in the target region first)

make deploy          # sync skills -> embed Lambdas -> deploy the whole stack
make stack-outputs   # console URL, webhook secret ARN, marker bucket, ...
```

`make deploy` auto-discovers the underlying EKS cluster name from the HyperPod
cluster's `Orchestrator.Eks.ClusterArn` and passes it in; you never set it by
hand. It also pre-flights the EKS auth mode (must be `API` or
`API_AND_CONFIG_MAP`) and aborts with the corrective command if not.

## Updating

- **Parameters / thresholds:** edit `deploy/params.json`, re-run `make deploy`.
- **Skills or the mental-model doc:** edit the file under `../skills/` (or
  `../../docs/hyperpod-mental-model.md`), then `make deploy`. `sync-skills`
  recomputes the content hash (`SkillsVersion`); the change makes CloudFormation
  re-run `SkillUploader`, which re-uploads only what changed.

## Operating

```bash
make bridge-logs2    # tail the webhook bridge Lambda
make audit-logs2     # tail the periodic-audit Lambda
make email-logs2     # tail the email notifier Lambda
make audit-test2     # invoke the periodic-audit Lambda once
make stack-status
```

## Teardown

```bash
make teardown-stack   # delete the stack (CRs disassociate the webhook + delete
                      # skills BEFORE the AgentSpace), then remove the assets bucket
```

## Parameters

Only three are required — `HyperPodClusterName`, `EmailSender`,
`EmailRecipients`. `EksClusterName`, `AssetsBucket`, `SkillsVersion`, and
`SkillsManifest` are filled in automatically by `make deploy` (do not set them in
`params.json`). Everything else has a safe default; see the inline `Description`
fields and the `AWS::CloudFormation::Interface` groups in
`hyperpod_devops_agent.yaml`.

## Multiple clusters in one account/region

Every collision-prone name is scoped per cluster, so you can deploy this stack
for several HyperPod clusters side by side without conflicts:

- **Stack name** defaults to `hyperpod-devops-agent-<slug>` (override with
  `STACK_NAME=...`).
- **S3 buckets** — `hpda-markers-<slug>-<account>-<region>` (created by the
  stack) and `hpda-assets-<slug>-<account>-<region>` (created by `make deploy`).
- **IAM roles** — the Agent Space + Webapp roles are CloudFormation
  auto-named by default (unique per stack). Set `AgentSpaceRoleName` /
  `WebappRoleName` only if you need fixed names.
- **Webhook secret** and **Agent Space** already include the cluster name.

`<slug>` is a lowercased, hyphenated, ≤20-char form of `HyperPodClusterName`
(e.g. `My_Prod-Cluster_01` → `my-prod-cluster-01`), derived identically by the
Makefile, `deploy.sh`, and `teardown.sh`. Everything else (Lambdas, EventBridge
rules, execution roles, the scheduler) is unnamed and CloudFormation auto-names
it per stack.

## Periodic audit — detection modes

The periodic audit runs on a schedule (default every 15 min) and can operate two
ways, chosen by `AuditDetectionMode`:

- **`lambda` (default):** the audit Lambda inspects cluster state itself —
  CrashLoopBackOff pods, NotReady nodes (both via read-only EKS API access), and
  open HyperPod fault chains (`list-cluster-events`) — and POSTs the DevOps Agent
  webhook **only when a real issue is found**. On a healthy cluster nothing is
  POSTed, so **no investigation runs and no cost is incurred**. A separate daily
  `AuditHeartbeatSchedule` fires one "all clear" investigation per day so
  operators can see the pipeline is alive.
- **`always-fire`:** legacy behavior — POST every audit and let the
  `hyperpod-incident-rca` skill discover issues and suppress on healthy clusters.
  Kept for comparison/rollback.

In `lambda` mode the Lambda has its **own** read-only `AWS::EKS::AccessEntry`
(distinct principal from the Agent Space role) carrying
`AmazonAIOpsAssistantPolicy` — note **not** `AmazonEKSViewPolicy`, whose `view`
role excludes cluster-scoped `nodes` and can't satisfy the NotReady-node check.
The Lambda calls the K8s API directly (SigV4 token + stdlib `urllib`) — no
`kubernetes` client or Lambda layer.

Audit investigation **titles are issue-descriptive and timestamp-free** (e.g.
`HyperPod k8-1: CrashLoopBackOff (crashloop-test/crashloop-canary:fail)`), so a
recurring issue produces an identical title and the platform/triage skill LINK or
SKIP the repeat instead of emailing every cycle.

Relevant params: `AuditDetectionMode` (`lambda`), `AuditSchedule`
(`rate(15 minutes)`), `HeartbeatSchedule` (`cron(0 12 * * ? *)`),
`K8sChecksEnabled` (`true`), `CrashLoopHoursThreshold` (4),
`NotReadyNodePercentThreshold` (10), `NotReadyDurationMinutes` (15).

## Slurm clusters

**Continuous Provisioning is a prerequisite for Slurm clusters.** Without it
(`NodeProvisioningMode` != `Continuous` in `describe-cluster`):

- `list-cluster-events` is **not supported** — the RCA skill reconstructs its
  incident timeline (replacement attempts, including failed ones) from this API,
  so its verdicts degrade badly without it.
- The HyperPod **EventBridge event format differs** from what the webhook bridge
  and skills expect, so live event bridging is unreliable.

`make deploy` checks `NodeProvisioningMode` for Slurm clusters and prints a loud
warning (but does not hard-fail) when it isn't `Continuous`. EKS-orchestrated
clusters are always Continuous, so this only affects Slurm. Enable Continuous
Provisioning on the cluster before relying on investigations.

Beyond that prerequisite: `make deploy` detects a Slurm cluster (no
`Orchestrator.Eks.ClusterArn`) and skips both EKS access entries (the Agent
Space role's and the audit Lambda's). In `lambda` detection mode on Slurm the
audit reduces to the `list-cluster-events` fault-chain check only — no
CrashLoop/NotReady checks (those are inherently EKS/kubectl). And because
`list-cluster-events` itself requires Continuous Provisioning, the audit has
little to inspect on a non-Continuous Slurm cluster. Validating the
Continuous-Provisioning Slurm path end-to-end is a follow-up (see the design
doc's "Still open" note).

Notable toggles: `EnablePeriodicAudit` (default `true`), `AuditDetectionMode`
(default `lambda`), `K8sChecksEnabled` (default `true`), `AuditSchedule`
(default `rate(15 minutes)`).
