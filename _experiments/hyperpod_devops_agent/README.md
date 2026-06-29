# HyperPod x AWS DevOps Agent

Wire any SageMaker HyperPod cluster into [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/) so cluster issues are auto-detected, investigated by the agent, classified against HyperPod's built-in resiliency behavior, and surfaced via email (and DevOps Agent's own notification channels).

## What this delivers

Four stacked pieces:

1. **Agent Space + EKS access** — gives the DevOps Agent read-only `kubectl` against the underlying EKS cluster (auto-discovered from the HyperPod cluster's `Orchestrator.Eks.ClusterArn`) and a console where investigations land. Slurm clusters skip the EKS step automatically.
2. **Webhook bridge** — CloudFormation stack with an EventBridge rule on `aws.sagemaker` HyperPod events and a Lambda that POSTs them to the DevOps Agent generic webhook. Supports a cluster allowlist so customers with multiple HyperPod clusters can scope which ones trigger investigations.
3. **`hyperpod-incident` skill** — unified triage + RCA skill that classifies each event against HyperPod's built-in resiliency model (read [docs/hyperpod-mental-model.md](../../docs/hyperpod-mental-model.md)). The skill decides per-incident whether HyperPod is auto-recovering (Suppress / Monitor) or stuck (Escalate), and produces a human-readable report with recommended operator actions.
4. **Email notifier** — CloudFormation stack: EventBridge rule on `aws.aidevops` investigation lifecycle events → Lambda → SES email. Recipients get a per-investigation message with the verdict, timeline, and recommended actions.

Slack notifications can be added later (paused on workspace 3P approval) via DevOps Agent's built-in Slack integration or via a sibling stack that listens on the same `aws.aidevops` event stream.

## Layout

```
.
├── Makefile                 - make targets for every step below
├── README.md                - this file
├── docs/                    - DevOps Agent UG + API ref PDFs (git-ignored) + extracted .txt
├── extract_pdf.py           - PDF -> .txt helper (pypdf)
├── requirements.txt
├── foundation/
│   └── template.yaml        - CloudFormation: IAM roles + AWS::DevOpsAgent::AgentSpace + AWS::DevOpsAgent::Association (AWS monitor)
├── webhook_bridge/
│   ├── template.yaml        - CloudFormation: EventBridge rule + Lambda + IAM
│   ├── lambda_function.py   - HyperPod event -> DevOps Agent payload
│   └── local_test.py        - send a synthetic event to the real webhook
├── email_notifier/
│   ├── template.yaml        - CloudFormation: EventBridge rule + Lambda + SES sender
│   └── lambda_function.py   - Investigation event -> formatted email
├── skills/
│   ├── hyperpod-incident/   - the unified triage + RCA skill (ours)
│   │   ├── SKILL.md
│   │   └── references/hyperpod-mental-model.md  - synced from ../../docs/ at upload time
│   └── upstream/            - awslabs/agent-plugins clone (git-ignored)
├── scripts/
│   ├── config.sh                 - shared config (env-overridable)
│   ├── 01_deploy_foundation.sh   - deploys foundation/template.yaml (CFN-native)
│   ├── 02_provision_webhook.sh   - register-service + associate-service (imperative — CFN gap)
│   ├── 03_grant_eks_access.sh    - skipped for Slurm clusters
│   ├── 04_create_webhook_secret.sh
│   ├── 05_deploy_webhook_bridge.sh
│   ├── 06_delete_webhook_bridge.sh
│   ├── 07_upload_skill.sh         - reads agent_types from SKILL.md frontmatter
│   ├── 08_delete_skill.sh
│   ├── 09_import_upstream_skills.sh  - curated allowlist (drops SSM-blocked skills)
│   ├── 10_deploy_email_notifier.sh
│   ├── 11_delete_email_notifier.sh
│   └── 99_teardown.sh
└── .state.json                    - written by setup, read by teardown (git-ignored)
```

## Prerequisites

- AWS CLI v2 configured for the target account, with a region set (`aws configure set region <region>`) or `REGION=<region>` exported.
- An existing HyperPod cluster (EKS or Slurm orchestrator). Set `HYPERPOD_CLUSTER_NAME` before any `make` target — the underlying EKS cluster name is auto-discovered, no need to set it manually.
- Permission to create IAM roles, manage Secrets Manager, deploy CloudFormation, call `devops-agent:*` + `eks:CreateAccessEntry`, and (for email) `ses:SendEmail` from a verified sender.

## Quick start

`HYPERPOD_CLUSTER_NAME` is required for every target. Export it once at the top of your shell:

```bash
export HYPERPOD_CLUSTER_NAME=<your-cluster-name>
# Optional overrides (everything else has a safe default or is auto-discovered):
#   REGION=<region> (else uses AWS CLI default)
#   EKS_CLUSTER_NAME=<name>  (else discovered from describe-cluster)
#   AGENT_SPACE_NAME=<name>  (else hyperpod-<cluster>-devops-agent)
```

```bash
make help                    # show every target
make config                  # show resolved config (region, role names, ...)
make check-aws               # whoami + caller identity
make check-cluster           # confirms HyperPod + EKS auth mode (EKS-orchestrated only)

# Step 1 - Foundation + webhook + EKS access (all in one)
make setup                   # foundation (CFN) -> provision-webhook -> eks-access (skipped for Slurm)
make status                  # print state file + Operator web app URL

# Step 2 - Stash the webhook credentials in Secrets Manager and deploy the bridge
make webhook-secret          # reads webhookUrl + webhookSecret from .state.json
                             #   (auto-populated by step 1); falls back to interactive prompt.
make deploy-bridge           # bridge filters to $HYPERPOD_CLUSTER_NAME by default;
                             #   CLUSTER_FILTER='a,b,c' make deploy-bridge to widen,
                             #   CLUSTER_FILTER='' make deploy-bridge to forward all.

# Step 3 - Smoke-test end to end
make bridge-test                                   # default: node-health event
LOCAL_EVENT_TYPE=cluster-state-change make bridge-test
make bridge-logs                                   # tail the Lambda logs (Ctrl-C to stop)

# Step 4 - Upload the unified hyperpod-incident skill (ours)
SKILL_DIR=skills/hyperpod-incident make upload-skill

# Step 5 - Optionally import a curated subset of upstream skills as reference
make import-upstream-skills                        # see "Skill curation" below for defaults
make list-skills

# Step 6 - Email notifications (SES sender must be verified in REGION)
EMAIL_SENDER=alerts@example.com \
EMAIL_RECIPIENTS=oncall@example.com,team@example.com \
    make deploy-email-notifier

# Teardown
make teardown                # email-notifier -> bridge -> EKS entry -> agent space + eventChannel -> IAM roles stack
DELETE_SECRET=yes make teardown   # also wipes the Secrets Manager secret
```

> **Webhook provisioning is fully automated** but stays imperative for
> the reason described in "What `make setup` creates" above. The HMAC
> secret returned by `associate-service` is only shown once — it lands
> in `.state.json` temporarily, gets copied to Secrets Manager by step 2,
> and is then stripped from the state file. If you ever need to recover
> the secret (e.g. teardown rolled back partway), you have to
> disassociate + re-associate to get a fresh one — the API doesn't
> expose the existing HMAC after creation.

## What `make setup` creates

`make foundation` deploys the CloudFormation stack `hyperpod-devops-agent-foundation` using **native `AWS::DevOpsAgent::*` resource types**:

| # | Resource (CFN type) | Why |
| --- | --- | --- |
| 1 | `AWS::IAM::Role` `DevOpsAgentRole-AgentSpace` | Assumed by `aidevops.amazonaws.com` to read AWS resources during investigations. Attaches managed policy `AIDevOpsAgentAccessPolicy` + inline policy allowing the Resource Explorer service-linked role to be created. Trust scoped to this account's `agentspace/*`. |
| 2 | `AWS::IAM::Role` `DevOpsAgentRole-WebappAdmin` | Backs the Operator web app. Attaches managed policy `AIDevOpsOperatorAppAccessPolicy`. |
| 3 | `AWS::DevOpsAgent::AgentSpace` `hyperpod-<cluster>-devops-agent` | Logical container for accounts, integrations, knowledge. `OperatorApp.Iam.OperatorAppRoleArn` set to the Webapp role — the operator web app is enabled in the same resource. |
| 4 | `AWS::DevOpsAgent::Association` (config `Aws`, accountType `monitor`) | Primary AWS account association. Turns on topology discovery across all regions of the account. |

`make provision-webhook` then runs `register-service eventChannel` + `associate-service` against the Agent Space, **imperatively**, because:
- `AWS::DevOpsAgent::Service` does not yet list `eventChannel` as an allowed `ServiceType` (only the OAuth/SaaS and MCP integrations are supported as of writing).
- Even when using `AWS::DevOpsAgent::Association` with an `EventChannel` configuration, **the generated webhook URL and HMAC secret are not exposed as `Fn::GetAtt` attributes** — there's no way to feed them into Secrets Manager from a CFN template.

`make eks-access` creates the EKS access entry (read-only `AmazonAIOpsAssistantPolicy`, cluster scope) — skipped for Slurm clusters.

## What `make deploy-bridge` creates

| Resource | Notes |
| --- | --- |
| Secrets Manager entry `hyperpod-devops-agent/webhook` | `{"url": "...", "secret": "..."}`. Created by `make webhook-secret` (not by the stack), so the values never appear in CloudFormation outputs. |
| CloudFormation stack `hyperpod-devops-agent-webhook-bridge` | Container for the rest. |
| Lambda execution role | Allows `secretsmanager:GetSecretValue` on the one secret + standard log permissions. |
| EventBridge → Lambda invoke role | Standard `lambda:InvokeFunction` trust. |
| Lambda function (Python 3.13, embedded code) | Reads the secret, builds a DevOps Agent incident payload, HMAC-signs it, POSTs. |
| EventBridge rule | Pattern: `source: aws.sagemaker`, detail-type: `SageMaker HyperPod Cluster State Change`, `... Cluster Node Health Event`, `... Cluster Event`. |

## Event → investigation payload mapping

| HyperPod detail-type | Investigation `priority` | Title | Description |
| --- | --- | --- | --- |
| Cluster State Change | `HIGH` for `Failed`/`RollingBack`, `LOW` for `Updating`/`Deleting`, else `MEDIUM` | `HyperPod cluster state: {name} -> {status}` | Includes instance-group counts. |
| Node Health Event | `HIGH` if status `Unhealthy`/`Degraded`, else `MEDIUM` | `HyperPod node health: {cluster}/{instance} -> {status}` | Includes `HealthStatusReason`, `RepairAction`, `Recommendation`. |
| Cluster Event | `MEDIUM` | `HyperPod cluster event: {cluster} / {resourceType}` | Includes `Description`, `InstanceGroupName`, `InstanceId`. |

`data.originalEvent` always carries the unmodified EventBridge event so the agent can dig in.

### Noise filter

HyperPod emits **many** `Info`-level "Cluster Event" entries during routine operations (each scale-up of `k8-1` produces 20+: `"Cluster k8-1 update started successfully"`, `"EKS Access Entries update successful"`, per-node provisioning notices, etc.). The Lambda drops events whose `detail.EventDetails.EventLevel` matches `WEBHOOK_DROP_EVENT_LEVELS` (default: `Info`). Without this filter a single +4 scale-up would burn ~20 investigations against the monthly quota.

`WEBHOOK_DROP_EVENT_LEVELS` (default `Info`) and `WEBHOOK_CLUSTER_FILTER` (default: only `$HYPERPOD_CLUSTER_NAME`, set via the `ClusterFilter` CFN parameter — empty = forward all clusters) are CloudFormation parameters on the bridge stack. To change either after deployment, redeploy with the override:

```bash
CLUSTER_FILTER='cluster-a,cluster-b' DROP_EVENT_LEVELS='Info,Debug' make deploy-bridge
```

Set `WEBHOOK_LOG_FULL_EVENT=true` to log the full EventBridge envelope per invocation (useful when discovering new event shapes; off by default).

`Cluster State Change` and `Node Health Event` payloads don't carry `EventLevel`, so they're never dropped by this filter — they should always trigger investigations.

## Knowledge: HyperPod skills in the Agent Space

DevOps Agent does not understand HyperPod out of the box — a HyperPod cluster is "a SageMaker resource" to its topology engine, not a composition of EKS + EC2 + FSx + lifecycle scripts. Two kinds of skill teach it the mapping:

1. **`hyperpod-incident` — our unified triage + RCA skill.** The primary skill loaded on every HyperPod investigation. Reads `describe-cluster`, `list-cluster-nodes`, `list-cluster-events`, and HMA CloudWatch streams; reconstructs a timeline; classifies as Suppress / Monitor / Escalate against time budgets derived from the [HyperPod mental model](../../docs/hyperpod-mental-model.md). Bundles the mental-model doc as a reference so the agent loads it into context. See [skills/hyperpod-incident/SKILL.md](skills/hyperpod-incident/SKILL.md).

2. **Curated upstream skills from [awslabs/agent-plugins](https://github.com/awslabs/agent-plugins)** — supporting reference. `make import-upstream-skills` imports a **curated subset** of the `hyperpod-*` skills (see "Skill curation" below). Use the `SKILLS=...` env var to import a different subset. Subsequent runs `git pull` upstream and re-upload.

### Skill curation: which upstream skills get uploaded

The default upload list excludes upstream skills whose entire procedure depends on SSM — those are unreachable inside the DevOps Agent permission guardrail (see "SSM access" below), and loading them confuses the agent with instructions it can't execute:

| Upstream skill | Default import? | Why |
| --- | --- | --- |
| `hyperpod-cluster-debugger` | yes | Cluster-level API + kubectl portions work in-guardrail |
| `hyperpod-node-debugger` | yes | API + kubectl node-state portions work in-guardrail |
| `hyperpod-nccl` | yes | API portions only — `kubectl logs`, training-op CRDs |
| `hyperpod-performance-debugger` | yes | API portions only — CloudWatch + EKS topology |
| `hyperpod-slurm-debugger` | **no** | Needs SSM to controller |
| `hyperpod-issue-report` | **no** | Whole skill is on-node collection |
| `hyperpod-version-checker` | **no** | Whole skill is on-node version reads |
| `hyperpod-ssm` | **no** | The SSM driver itself |

Override with `SKILLS='hyperpod-nccl hyperpod-node-debugger' make import-upstream-skills` to import a custom subset. Override `UPSTREAM_REF` to pin to a specific commit/branch/tag.

### Authoring your own skill

The `07_upload_skill.sh` and `08_delete_skill.sh` scripts are general-purpose. To author a custom skill, drop a directory under `skills/` containing a `SKILL.md` (with frontmatter `name:`, `description:`, and `metadata.agent_types:` as a list) plus optional `references/` markdown files, then run `SKILL_DIR=skills/my-skill make upload-skill`. The upload script reads `agent_types` from the SKILL.md frontmatter — set it to `["INCIDENT_TRIAGE", "INCIDENT_RCA"]` for skills that should be loaded during investigations (DevOps Agent matches the trigger type against `agent_types`).

To remove: `SKILL_NAME=my-skill make delete-skill`. The skill's `description:` field determines when the agent loads it during investigations.

The upstream skills were authored for Claude Code / Codex runtimes that can execute shell directly on HyperPod nodes. **DevOps Agent's runtime cannot, and adding IAM permissions does not change that.** The constraint is an AWS-published "permission guardrail" — a fixed session policy applied at AssumeRole time — that intersects with the IAM role and overrides anything you grant.

### SSM access — the permission guardrail is a hard ceiling

The DevOps Agent UG (p. 365–367, "Understanding permission guardrails") states this verbatim:

> *"AWS DevOps Agent applies a permission guardrail to every session it creates when accessing your AWS resources. This guardrail acts as a ceiling — it defines the maximum set of permissions the agent can ever use, regardless of what permissions you grant on the IAM role."*
>
> *"Permissions not listed here or in the `AIDevOpsAgentAccessPolicy` managed policy are blocked by the guardrail."*

Three layers stack at AssumeRole time:

| Layer | Who controls | Purpose |
| --- | --- | --- |
| IAM role policies | You | What you intend the agent to be able to do |
| Permission guardrail (session policy) | **AWS DevOps Agent** | The maximum the agent can ever do |
| Effective permissions | Intersection of both | What the agent can actually do |

The guardrail contains everything in `AIDevOpsAgentAccessPolicy` (the default read-only set) plus a **closed allowlist** of opt-in permissions you can enable by adding them to your role. The complete allowlist from the UG:

| Service | Actions | Use case |
| --- | --- | --- |
| Athena | `athena:GetQuery*`, `athena:StartQueryExecution`, `athena:StopQueryExecution` | Run queries against your data catalog |
| S3 | `s3:GetObject`, `s3:ListBucket` | Read application data, logs, configs |
| Direct Connect | `directconnect:Describe*` | Investigate network connectivity |
| Glue | `glue:GetPartitions` | Read partition metadata for Athena |
| KMS | `kms:Decrypt` | Decrypt encrypted resources |

`ssm:StartSession` and `ssm:SendCommand` are NOT in the allowlist, and `AIDevOpsAgentAccessPolicy` does not include them either. **The guardrail strips them from the session regardless of what you grant on the role.**

### What we observed empirically

We confirmed this end-to-end. The experiment:

1. Attached a scoped inline policy on `DevOpsAgentRole-AgentSpace` granting `ssm:StartSession` against the HyperPod cluster ARN and the `AWS-StartNonInteractiveCommand` document ARN. (The grant/revoke scripts have since been removed from this repo since SSM is permanently outside the guardrail; the policy itself is recorded below for reference.)
2. Asked the agent in chat: *"Run `nvidia-smi -L` on instance `i-080f90acad180de3e` via SSM."*
3. Agent loaded the `hyperpod-ssm` skill, called `sagemaker:describe_cluster` to resolve the cluster ID, built the correct target string `sagemaker-cluster:lw12e0dn1hhd_worker3-i-080f90acad180de3e`, and attempted `ssm:start_session` with document `AWS-StartNonInteractiveCommand` and the right parameters.
4. **The call was blocked before reaching AWS.** Agent reported: *"The SSM `start_session` operation was blocked because it requires operator approval — it's classified as a mutative operation."*

So the agent's tool surface accepts the call (it's a real `use_aws` invocation against `ssm:StartSession`), but the session policy strips the permission, surfacing as "requires operator approval / mutative". This is the guardrail doing its job.

We've revoked the inline policy. It had no effect on agent behavior — kept only as a reminder that customer IAM isn't the lever here.

### How the upstream skills work around it (for reference)

The upstream `hyperpod-*` skills use `ssm:StartSession` with the AWS-managed `AWS-StartNonInteractiveCommand` document. From `skills/upstream/plugins/sagemaker-ai/skills/hyperpod-ssm/scripts/ssm-exec.sh`:

```
aws ssm start-session \
  --target sagemaker-cluster:<cluster-id>_<group>-<instance-id> \
  --document-name AWS-StartNonInteractiveCommand \
  --parameters '{"command":["nvidia-smi"]}'
```

Functionally this is "send me a command, give me the stdout" — but it's `StartSession` under the hood (HyperPod targets don't accept `SendCommand` either, per the internal HyperPod mental model doc). The `unbuffer` wrapper in the upstream script is a workaround for an SSM PTY race ([aws/amazon-ssm-agent#358](https://github.com/aws/amazon-ssm-agent/issues/358)), not a HyperPod thing.

This pattern works for Claude Code / Codex (which call the AWS CLI directly with the session-manager-plugin) but is unreachable from DevOps Agent because of the guardrail.

### Impact on the imported skills

| Skill | Pure AWS-API / kubectl portion | On-node portion (requires SSM session with stdin) |
| --- | --- | --- |
| `hyperpod-cluster-debugger` | works | n/a |
| `hyperpod-nccl` | works | **blocked at guardrail** (EFA / libfabric / `dmesg` probes) |
| `hyperpod-node-debugger` | works | **blocked at guardrail** (DCGM / Xid / kubelet journal) |
| `hyperpod-performance-debugger` | works | **blocked at guardrail** (per-node throughput probes) |
| `hyperpod-slurm-debugger` | works | **blocked at guardrail** (slurmctld logs, `scontrol` from controller) |
| `hyperpod-issue-report` | n/a | **blocked at guardrail** (whole skill is on-node collection) |
| `hyperpod-version-checker` | n/a | **blocked at guardrail** (whole skill is on-node version reads) |
| `hyperpod-ssm` | n/a | **blocked at guardrail** (whole skill is the SSM driver) |

### Why this matters operationally

The HyperPod ops doc enumerates ground-truth signals that **only** live on the node: NVIDIA Xid lines in `dmesg`, DCGM correctable/uncorrectable ECC counters, EFA fabric errors, kubelet journal, `slurmctld.log`, lifecycle script output to `/var/log/provision/provisioning.log`, NVMe / `/opt/dlami` state, GPU thermal throttling. Many of these are the exact failure modes (Xid 74/79, ECC UCE, EFA health-check failure, lifecycle script failure) that drive HyperPod replacements.

Without an on-node path, DevOps Agent's investigations have to either:

- **Reason from proxies**: HMA-generated CloudWatch log streams (`SagemakerHealthMonitoringAgent/<group>/<instance>` in `/aws/sagemaker/Clusters/<name>/<id>`), K8s node labels (`sagemaker.amazonaws.com/fault-types`, `fault-reasons`, `node-health-status`), `list-cluster-events`, `sinfo` / `kubectl describe node`. These often surface *the conclusion* (HMA already classified the fault) without the underlying evidence.
- **Lose**: for the long tail where HMA didn't classify the failure (custom workloads, NCCL hangs, slow storage, dropped LCS output), DevOps Agent will not see the on-node signal at all.

The proxy path is sufficient for HMA-classified faults. The Xid 79 fault-injection test we ran (HMA → `NvidiaGPUUnhealthy` → `Cluster Event` Warn → investigation) is the canonical example — the agent didn't need on-node access because HMA's classification was already in the control-plane event.

### Workarounds (none built yet)

Because the guardrail is fixed by AWS, the only realistic paths are **side-loading on-node data into surfaces the guardrail already permits**:

1. **External collector → CloudWatch Logs.** A Lambda or cron uses `StartSession` + `AWS-StartNonInteractiveCommand` (the [`hyperpod_run_on_multi_nodes.py`](../../hyperpod_run_on_multi_nodes/) pattern in this repo), runs a fixed read-only diagnostic script on each node, writes output to a CloudWatch Logs group. The agent reads via `logs:FilterLogEvents` which IS in the guardrail. SSM throttle is 3 TPS — fan-out must serialize or back off.
2. **Periodic snapshot to S3.** Same shape, but writes structured JSON to a versioned S3 prefix. Agent reads via `s3:GetObject` (which is in the guardrail's opt-in allowlist — must be added to the role explicitly). Better for time-series reconstruction across investigations.
3. **On-demand collector before investigation.** The HyperPod EventBridge → webhook bridge invokes the collector first, waits for output to land in CloudWatch Logs, then fires the investigation webhook. Highest fidelity, every investigation pays the collector's wall-clock.

Either branch needs the agent to be told *where* the on-node data lives — additions to a HyperPod-specific skill that say "for on-node DCGM state, query `logs:FilterLogEvents` against log group `/aws/hyperpod-collector/...`" or similar.

### Should we ask AWS to change the guardrail?

This is the real revisit. The guardrail is not a bug — it's AWS's deliberate ceiling for blast-radius from prompt injection (the same reason the Azure integration only allows the Reader role; UG p. 216). But for HyperPod specifically, the on-node signals are operationally critical and the alternative (every customer building a collector) is infrastructure tax for what's really an AWS-internal capability gap.

A reasonable ask would be: **add `ssm:StartSession` to the guardrail allowlist, scoped to `arn:aws:ssm:*::document/AWS-StartNonInteractiveCommand`** (so only the non-interactive command document is reachable, never a full shell). That keeps the prompt-injection blast radius bounded to "run a customer-defined command" rather than "drop into an interactive shell" — comparable to what `s3:GetObject` already permits.

Filing that as feedback to ASBX is the most leveraged next action. Tracked as a follow-up; not yet sent. None of the side-load paths are built either — the AWS-API/kubectl portions of the imported skills still work and cover the HMA-classified failure modes, which is most of what we'd auto-trigger investigations on anyway.

Two coexisting skill types you'll see in `make list-skills`:
- **USER** — what we author (this repo). Edits are deliberate.
- **LEARNED** — what the agent generates about your environment over time (e.g. `understanding-agent-space`). Don't touch these; they reflect what the agent already figured out.

## How notifications work

Three channels stack:

1. **Email (via SES)** — deployed by `make deploy-email-notifier`. EventBridge rule on `source: aws.aidevops`, detail-type prefix `Investigation` → Lambda → `ses:SendEmail` to the configured recipients. By default sends on `Investigation Created` and `Investigation Closed` (skips `Investigation Updated` to avoid spam); override with `EMAIL_DETAIL_TYPES`. The email body includes the verdict, recommended actions, and a console link.
   - SES sender must be verified in `$REGION`. If SES is in sandbox mode, every recipient must also be verified.
   - The IAM policy on the Lambda restricts `ses:SendEmail` to the configured `EMAIL_SENDER` via the `ses:FromAddress` condition.
2. **DevOps Agent web app** — every investigation is visible at the Agent Space console URL printed by `make status`.
3. **Slack / ServiceNow / PagerDuty / Microsoft Teams** — configure once in the Agent Space console (paused on workspace 3P approval for the originating project). The same `aws.aidevops` event stream the email notifier listens on is available for any additional fan-out.

## Findings from the DevOps Agent docs (anchor for design)

DevOps Agent is **alert-driven, not polling**. Investigations only run when something triggers them: a webhook, a ticket integration, a third-party SaaS hook, or a manual click. Out of the box it has no concept of "watch HyperPod" — that's why the webhook bridge exists.

Integration surfaces relevant to HyperPod:

| Surface | Direction | Used here? |
| --- | --- | --- |
| **EKS access entry** | Pull | Yes — read-only `kubectl` against the underlying EKS cluster. |
| **Generic webhook** (HMAC) | Into the agent | Yes — every HyperPod event triggers an investigation. |
| **EventBridge `aws.aidevops`** | From the agent | Yes — the email notifier listens on `Investigation` detail-types and sends SES email. |
| **Skills** (asset API) | Inside the agent | Yes — our `hyperpod-incident` skill is the primary investigation driver; a curated subset of upstream `hyperpod-*` skills is imported as supporting reference. |

Operating notes:

- **Agent Space region** — Agent Space is available in a fixed set of regions; check `aidevops.<region>.amazonaws.com` resolves before running. The chosen region applies to the Agent Space resource itself; cross-region monitoring is implicit (one Agent Space discovers resources across every region of the associated account).
- **Quotas (per the UG)**: 100 agent spaces / region, 3 concurrent investigations / space (adjustable), 10 concurrent on-demand invocations / space.
- **EKS access prerequisite** — the underlying EKS cluster's `authenticationMode` must be `API` or `API_AND_CONFIG_MAP`. The setup script verifies this and aborts with the corrective `update-cluster-config` command if not.

## The `hyperpod-incident` skill — unified triage + RCA

The original plan called for separate triage and investigation skills. **They were merged.** A single failed instance can vanish from `list-cluster-nodes` between retry attempts, and HyperPod may auto-retry from `Failed` status — neither is a terminal signal on its own. Distinguishing "still retrying" from "stuck" requires the full timeline across `describe-cluster`, `list-cluster-nodes`, `list-cluster-events` (the canonical record of replacement attempts, including failed ones; available on EKS and on Slurm with Continuous Provisioning), and HMA CloudWatch streams. A separate triage skill that decided without all four signals would systematically miss the case where multiple replacements have already failed silently.

The skill classifies each event into one of these verdicts:

| Verdict | Meaning |
| --- | --- |
| `Suppress` | Routine `Info`-level activity; no investigation produced. |
| `Monitor — first attempt` | Recovery in flight, first attempt, within the 30 min budget. Next re-check timestamp included. |
| `Monitor — elevated` | Multiple retry attempts in flight, total elapsed ≤ 90 min. Recovery may still succeed; user is notified so they're not surprised. |
| `Escalate` | Recovery is stuck (no new attempt within 30 min, total elapsed > budget), HyperPod has given up (`Failed` with no new attempt), or instance vanished with no retry. Operator action required. |

`Monitor` verdicts are not silent — the email tells the user "HyperPod is auto-recovering, expected completion by HH:MM UTC, you'll be notified again only if the situation changes." The follow-up only fires if the verdict transitions on a later event.

Time budgets in the skill encode the "How long things take" table in the [HyperPod mental model](../../docs/hyperpod-mental-model.md). Update the mental-model doc first if the budgets need to change.

## Two operational goals the current solution does NOT yet meet

Validated end-to-end with an Xid 74 fault injection on `worker2`: the skill loads, runs Phase 1 parallel gather across four signal sources, classifies as `Monitor — first attempt`, and emits a structured report with verdict + timeline + confidence annotations. **But two operational requirements are not yet met by the deployed solution:**

### Goal 1: monitor incident duration; escalate if it lasts too long

DevOps Agent runs a **single-shot investigation** per webhook trigger. When the skill emits a `Monitor` verdict, the agent writes the report, declares the investigation `COMPLETED`, and exits. It does NOT come back to:
- Confirm the replacement EC2 actually launched
- Verify the new node reached `Running`
- Catch the case where HyperPod silently dropped into `Failed` after the initial detection
- Notify the human when recovery cleanly succeeds (silent-success closure)

The skill's "Next re-check: HH:MM UTC" line in the verdict is a promise to the human, not a self-scheduled callback.

### Goal 2: detect statistically recurring patterns even when each occurrence auto-resolves

Each individual incident may classify cleanly as `Monitor — first attempt` and auto-resolve, but if the **same Xid signature hits the same instance group three times in a week**, that pattern matters and the operator needs to know — the surface-level recovery doesn't mean the underlying problem is benign.

The v4 skill noticed this incidentally on a single incident (it flagged the recurring Xid 74 on consecutive worker2 instances as a `hypothesis` finding because both instances were in the journal's lookback). This needs to be promoted from incidental to a first-class classification rule.

## Solution ideas (ranked by leverage)

These extend, not replace, the current EventBridge → bridge Lambda → webhook trigger path. Other trigger sources DevOps Agent supports that we could also use:

| Trigger source | Why we'd use it |
|---|---|
| **EventBridge → webhook** (today) | Real-time HyperPod control-plane state changes |
| **CloudWatch Logs subscription filter on the HMA stream → webhook** | Faster + more granular than the SageMaker EventBridge `Cluster Event` Warn — catches HMA detections that don't always surface as control-plane events, and lets us filter on specific Xid codes / ECC counts / LCS-script failures |
| **CloudWatch metric alarm → SNS → webhook** | Threshold-crossing semantics for statistical patterns ("3 replacements on this IG in 7 days") |
| **EventBridge Scheduler → webhook** | Time-based per-incident re-checks and recurring pattern audits |
| **`devops-agent create-trigger` with `schedule`** | Agent-internal scheduled re-firing — same shape as EventBridge Scheduler but stays inside the platform. Worth trying first; fall back to external if it doesn't fit the per-incident pattern |

Ranked by leverage:

1. **(Goal 2, lightweight) Sliding-window rule inside the existing skill.** Phase 1 already paginates `list-cluster-events`. Extend the lookback to 7 days, count `Replace` actions per InstanceGroup and per Xid code, and add classification rules:
   - "≥3 replacements with same Xid signature on same IG in 7 days, even with auto-recovery succeeding each time → `Monitor — recurring pattern, hardware investigation recommended`"
   - "≥5 replacements across any node in 24 hours → `Escalate — fleet-wide instability`"

   Zero new infrastructure. Just skill prose + a classification table extension. Catches Goal 2 for any incident the agent investigates.

2. **(Goal 1) EventBridge Scheduler + DynamoDB for per-incident re-check.**
   - When the skill emits a `Monitor` verdict, the bridge (or a helper Lambda the skill nudges) writes a row: `(incident_id, cluster, instance_id, first_seen, next_recheck_at, current_verdict)`.
   - An EventBridge Scheduler rule fires a Lambda every 5 min. The Lambda finds rows where `now > next_recheck_at`, synthesizes a "re-check" event, and POSTs the webhook.
   - The skill, on re-invocation with a re-check event, sees the same cluster + instance, re-classifies. If recovery completed → emit `Resolved` symptom (and the Lambda deletes the row). If still in flight past 90 min total elapsed → escalate.
   - **Try DevOps Agent's `create-trigger` API first** (we saw it in the CLI help: `--type` + `--condition schedule={expression=...}` + `--action`). If it supports per-incident scheduled re-fire with custom payload, prefer that — fewer moving parts, stays inside the platform.
   - This is the missing piece for the "silent-success closure" notification — without it, customers only ever get the initial "Monitor" email and never see a "resolved" confirmation.

3. **(Stronger signal) CloudWatch Logs subscription filter on HMA stream as an additional trigger source.** Adds a faster + more granular trigger path that catches HMA detections SageMaker doesn't always surface as `Cluster Event` Warn. Worth doing once #1 and #2 are in.

4. **(Goal 2, heavier) Independent scheduled pattern audit.** EventBridge Scheduler → Lambda → webhook fires every 12 hours with a "pattern audit" trigger event. Skill, given this trigger type, runs Phase 1 with a wider window (7-30 days) and produces a verdict of `Pattern audit: N replacements in window, top causes X`. Lands as a periodic digest. Catches patterns that span many different nodes — invisible from any single-incident view. Build only if #1 doesn't catch the patterns customers actually report.

5. **Slack channel for live investigation updates** — paused on workspace 3P approval. The email notifier's EventBridge listener is the template; a Slack notifier drops into the same `aws.aidevops` event stream.

6. **External diagnostic collector** (see [SSM access — the permission guardrail is a hard ceiling](#ssm-access--the-permission-guardrail-is-a-hard-ceiling) above). Would side-load on-node truth (DCGM, EFA fabric counters, kubelet journal) into CloudWatch Logs or S3 where the guardrail can read them. Build only if a future investigation hits a wall the proxy-signal path can't reach.

7. **Per-failure-mode RCA skills** beyond `hyperpod-incident` — narrower skills (NCCL hang, slow storage, lifecycle-script failure) loaded only when the unified skill's classification matches. The current bet is that the unified skill plus the upstream cluster/node debuggers cover most cases; branch out only if specific failure modes prove to need deeper specialization.
- **Slurm coverage validation end-to-end** — the skill is written to work for Slurm with Continuous Provisioning, but the empirical testing so far is EKS-only.
