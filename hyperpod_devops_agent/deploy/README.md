# Single-template deployment

One CloudFormation stack that deploys the entire HyperPod × AWS DevOps Agent
solution — foundation (IAM roles + Agent Space + AWS-monitor association), EKS
read-only access, the webhook bridge, the periodic audit, the email notifier,
and the two skills.

## Why two custom resources

Everything is deployed with official resource types **except** two gaps that
CloudFormation cannot express:

1. **eventChannel webhook** — `AWS::DevOpsAgent::Service` has no `eventChannel`
   ServiceType, and `AWS::DevOpsAgent::Association` with an `EventChannel`
   configuration does not expose the generated webhook URL / HMAC secret as a
   `Fn::GetAtt`. → `Custom::WebhookProvisioner` (register/associate + stash the
   secret into Secrets Manager).
2. **Skill assets** — there is no `AWS::DevOpsAgent::Asset` resource type.
   → `Custom::SkillUploader` (create/update/delete skill assets from S3).

The EKS access grant is the native `AWS::EKS::AccessEntry` (skipped automatically
for Slurm clusters).

## Layout

```
deploy/
  hyperpod_devops_agent.yaml           - the deployable template (Lambda code inlined; committed)
  hyperpod_devops_agent.template.yaml  - the source template (with # *_CODE_PLACEHOLDER markers)
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
`# <NAME>_CODE_PLACEHOLDER` marker in `hyperpod_devops_agent.template.yaml`,
producing the deployable `hyperpod_devops_agent.yaml` (committed — this is the
file customers download and deploy directly; they don't need the template).

## Quick start

```bash
cd hyperpod_devops_agent
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
  `../docs/hyperpod-mental-model.md`), then `make deploy`. `sync-skills`
  recomputes the content hash (`SkillsVersion`); the change makes CloudFormation
  re-run `SkillUploader`, which re-uploads only what changed.

## Operating

```bash
make bridge-logs    # tail the webhook bridge Lambda
make audit-logs     # tail the periodic-audit Lambda
make email-logs     # tail the email notifier Lambda
make audit-test     # invoke the periodic-audit Lambda once
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
`hyperpod_devops_agent.template.yaml`.

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

**Division of labor:** HyperPod control-plane faults (node health, capacity
errors, lifecycle-script failures, cluster state changes) are handled
**event-driven by the webhook bridge** — it reads the native `EventLevel` from the
EventBridge event and forwards the real FailureMessage, for both EKS and Slurm.
The periodic audit covers only what the event stream **cannot**: Kubernetes
Pod/Node state, which is not in the HyperPod event stream.

The audit runs on a schedule (default every 15 min), mode chosen by
`AuditDetectionMode`:

- **`lambda` (default):** the audit Lambda inspects Kubernetes state —
  CrashLoopBackOff pods and NotReady nodes (via read-only EKS API access) — and
  POSTs the DevOps Agent webhook **only when a real issue is found**. On a healthy
  cluster nothing is POSTed, so **no investigation runs and no cost is incurred**.
  A separate daily `AuditHeartbeatSchedule` fires one "all clear" investigation
  per day so operators can see the pipeline is alive. **On Slurm (no kubectl) the
  audit has nothing to poll, so it fires only the heartbeat** — HyperPod faults
  on Slurm still flow through the event-driven bridge.
- **`always-fire`:** an alternative mode — POST every audit and let the
  `hyperpod-incident-rca` skill discover issues and suppress on healthy clusters.
  Costs one investigation per audit cycle even when the cluster is healthy.

The audit deliberately does **not** re-scan `list-cluster-events` for faults: that
duplicated the bridge from a worse data source (the Lambda runtime's boto3 omits
`EventLevel` on that API, which would force fragile hardcoded fault-string
matching).

In `lambda` mode the Lambda has its **own** read-only `AWS::EKS::AccessEntry`
(distinct principal from the Agent Space role) carrying
`AmazonAIOpsAssistantPolicy` — note **not** `AmazonEKSViewPolicy`, whose `view`
role excludes cluster-scoped `nodes` and can't satisfy the NotReady-node check.
The Lambda calls the K8s API directly (SigV4 token + stdlib `urllib`) — no
`kubernetes` client or Lambda layer.

Audit investigation **titles are issue-descriptive and timestamp-free** (e.g.
`HyperPod my-cluster: CrashLoopBackOff (my-namespace/my-pod)`), so a
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
Space role's and the audit Lambda's). On Slurm the periodic audit has no
Kubernetes to poll, so it fires **only the daily heartbeat** — all HyperPod
faults (capacity, node health, lifecycle-script, cluster state) flow through the
**event-driven bridge**, which works on Slurm as long as Continuous Provisioning
is enabled. On a Continuous Slurm cluster, a capacity-error fault is caught and
notified via the bridge with a specific "What happened" email subject; the audit
stays out of it and the heartbeat fires as expected.

Notable toggles: `EnablePeriodicAudit` (default `true`), `AuditDetectionMode`
(default `lambda`), `K8sChecksEnabled` (default `true`), `AuditSchedule`
(default `rate(15 minutes)`).
