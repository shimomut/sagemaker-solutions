# HyperPod x AWS DevOps Agent — experiment

Wire SageMaker HyperPod (EKS-orchestrated cluster `k8-1`) into [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/) so cluster issues are auto-detected, investigated by the agent, and surfaced through DevOps Agent's own notification channels.

## What this delivers

Two stacked pieces:

1. **Agent Space + EKS access** — gives the DevOps Agent read-only `kubectl` against the underlying EKS cluster and a console where investigations land.
2. **Webhook bridge** — a CloudFormation stack with an EventBridge rule on `aws.sagemaker` HyperPod events and a Lambda that POSTs them to the DevOps Agent generic webhook. When a HyperPod event fires (cluster state change, node health, generic cluster event), an investigation auto-starts.

Notifications about investigation outcomes are handled by **DevOps Agent**: configure Slack / ServiceNow / PagerDuty / EventBridge in the Agent Space console. Anything emitted on `source: aws.aidevops` lifecycle events can be fanned out further with your own EventBridge rules.

## Layout

```
.
├── Makefile                 - make targets for every step below
├── README.md                - this file
├── docs/                    - DevOps Agent UG + API ref PDFs (git-ignored) + extracted .txt
├── extract_pdf.py           - PDF -> .txt helper (pypdf)
├── requirements.txt
├── scripts/
│   ├── config.sh            - shared config (env-overridable)
│   ├── 01_create_iam_roles.sh
│   ├── 02_create_agent_space.sh
│   ├── 03_grant_eks_access.sh
│   ├── 04_create_webhook_secret.sh
│   ├── 05_deploy_webhook_bridge.sh
│   ├── 06_delete_webhook_bridge.sh
│   └── 99_teardown.sh
├── webhook_bridge/
│   ├── template.yaml          - CloudFormation: EventBridge rule + Lambda + IAM
│   ├── lambda_function.py     - HyperPod event -> DevOps Agent payload
│   ├── local_test.py          - send a synthetic event to the real webhook
│   └── template.embedded.yaml - generated; the rendered template
├── skills/
│   └── upstream/              - awslabs/agent-plugins clone (git-ignored; populated by make import-upstream-skills)
└── .state.json                - written by setup, read by teardown (git-ignored)
```

## Prerequisites

- AWS CLI v2 configured for the target account.
- HyperPod cluster `k8-1` in `us-west-2` (account 842413447717) — already exists.
- Permission to create IAM roles, manage Secrets Manager, deploy CloudFormation, and call `devops-agent:*` + `eks:CreateAccessEntry`.

## Quick start

```bash
make help                    # show every target
make extract-docs            # one-time: build searchable .txt from the PDFs

make check-aws               # whoami + caller identity
make check-cluster           # confirms HyperPod + EKS auth mode
make config                  # show resolved config (region, role names, ...)

# Step 1 - Agent Space + EKS access
make setup                   # iam-roles -> agent-space -> eks-access
make status                  # print state file + Operator web app URL

# Step 2 - Generate the DevOps Agent webhook (manual, one-time)
#   Open the Agent Space in the console (URL printed by 'make status'):
#     -> Capabilities tab
#     -> Webhook section -> Configure -> Generate webhook
#     -> Copy the webhook URL and HMAC secret (shown only once!)

# Step 3 - Store the webhook credentials and deploy the bridge
WEBHOOK_URL='https://event-ai.us-west-2.api.aws/webhook/generic/...' \
WEBHOOK_HMAC_SECRET='...' \
    make webhook-secret
make deploy-bridge

# Step 4 - Smoke-test end to end
make bridge-test                                   # default: node-health event
LOCAL_EVENT_TYPE=cluster-state-change make bridge-test
make bridge-logs                                   # tail the Lambda logs (Ctrl-C to stop)

# Step 5 - Import upstream HyperPod skills from awslabs/agent-plugins
make import-upstream-skills                        # clones repo, strips scripts/, uploads each
make list-skills                                   # show all skills + their type (USER vs LEARNED)
# SKILLS='hyperpod-nccl hyperpod-node-debugger' make import-upstream-skills  # subset
# To remove a single skill by name: SKILL_NAME=hyperpod-nccl make delete-skill

# Teardown
make teardown                # bridge stack -> EKS entry -> agent space -> IAM roles
DELETE_SECRET=yes make teardown   # also wipes the Secrets Manager secret
```

To override defaults, export before running:

```bash
REGION=us-west-2 \
HYPERPOD_CLUSTER_NAME=k8-1 \
EKS_CLUSTER_NAME=sagemaker-k8-1-1bd2626f-eks \
AGENT_SPACE_NAME=hyperpod-devops-agent-poc \
make setup
```

## What `make setup` creates

| # | Resource | Why |
| --- | --- | --- |
| 1 | IAM role `DevOpsAgentRole-AgentSpace` | Assumed by `aidevops.amazonaws.com` to read AWS resources during investigations. Attaches managed policy `AIDevOpsAgentAccessPolicy` + inline policy allowing the Resource Explorer service-linked role to be created. Trust scoped to this account's `agentspace/*`. |
| 2 | IAM role `DevOpsAgentRole-WebappAdmin` | Backs the Operator web app. Attaches managed policy `AIDevOpsOperatorAppAccessPolicy`. |
| 3 | Agent Space `hyperpod-devops-agent-poc` (us-west-2) | Logical container for accounts, integrations, knowledge. |
| 4 | Primary account association (`accountType=monitor`) | Turns on topology discovery across all regions of the account. |
| 5 | Operator web app (auth flow `iam`) | UI entry point. |
| 6 | EKS access entry on `sagemaker-k8-1-1bd2626f-eks` | Read-only kubectl via `AmazonAIOpsAssistantPolicy`, cluster scope. |

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

To change which levels are dropped at runtime (no redeploy needed), update the Lambda env var:

```bash
aws lambda update-function-configuration --region us-west-2 \
  --function-name <function-name-from-make-status> \
  --environment "Variables={WEBHOOK_SECRET_ARN=...,WEBHOOK_DROP_EVENT_LEVELS=Info,Debug}"
```

Set `WEBHOOK_LOG_FULL_EVENT=true` to log the full EventBridge envelope per invocation (useful when discovering new event shapes; off by default).

`Cluster State Change` and `Node Health Event` payloads don't carry `EventLevel`, so they're never dropped by this filter — they should always trigger investigations.

## Knowledge: HyperPod skills in the Agent Space

DevOps Agent does not understand HyperPod out of the box — a HyperPod cluster is "a SageMaker resource" to its topology engine, not a composition of EKS + EC2 + FSx + lifecycle scripts. We import upstream skills from [awslabs/agent-plugins](https://github.com/awslabs/agent-plugins) to teach it that mapping.

### Importing the upstream `awslabs/agent-plugins` HyperPod skills

`make import-upstream-skills` clones [awslabs/agent-plugins](https://github.com/awslabs/agent-plugins) into `skills/upstream/` (git-ignored), strips each skill's `scripts/` directory (DevOps Agent skills are explicitly "non-executable documents"), and uploads every `hyperpod-*` skill via `create-asset` / `update-asset`. Subsequent runs `git pull` and re-upload the latest version — version control sits in upstream.

Subset to one or a few skills with the `SKILLS` env var: `SKILLS='hyperpod-nccl' make import-upstream-skills`. Override `UPSTREAM_REF` to pin to a specific commit/branch/tag.

### Authoring your own skill

The `07_upload_skill.sh` and `08_delete_skill.sh` scripts are general-purpose. To author a custom skill, drop a directory under `skills/` containing a `SKILL.md` (with frontmatter `name:` and `description:`) plus optional `references/` markdown files, then run `SKILL_DIR=skills/my-skill make upload-skill`. To remove: `SKILL_NAME=my-skill make delete-skill`. The skill's `description:` field determines when the agent loads it during investigations.

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

This experiment **does not** add custom notification fan-out. Use what DevOps Agent already provides:

- **Web app**: every investigation is visible at the Agent Space console URL printed by `make status`.
- **Slack / ServiceNow / PagerDuty / Microsoft Teams**: configure once in the Agent Space console; investigations triggered by the webhook bridge will produce updates in those channels automatically.
- **EventBridge passthrough**: add your own rule on `source: aws.aidevops`, detail-type prefix `Investigation` to route lifecycle events into SNS / Lambda / SES / etc. The repo's [hyperpod_events/](../../hyperpod_events/) is the established pattern for that style of fan-out.

## Findings from the DevOps Agent docs (anchor for design)

DevOps Agent is **alert-driven, not polling**. Investigations only run when something triggers them: a webhook, a ticket integration, a third-party SaaS hook, or a manual click. Out of the box it has no concept of "watch HyperPod" — that's why the webhook bridge exists.

Integration surfaces relevant to HyperPod:

| Surface | Direction | Used here? |
| --- | --- | --- |
| **EKS access entry** | Pull | Yes — read-only `kubectl` against the underlying EKS cluster. |
| **Generic webhook** (HMAC) | Into the agent | Yes — every HyperPod event triggers an investigation. |
| **EventBridge `aws.aidevops`** | From the agent | Not used here. Add your own rules for downstream notifications. |
| **Skills** (asset API) | Inside the agent | Yes — 8 upstream `hyperpod-*` skills from awslabs/agent-plugins are imported via `make import-upstream-skills`. |

Confirmed for our environment:

- **us-west-2 is a supported Agent Space region** (`aidevops.us-west-2.amazonaws.com`).
- **Quotas are non-blocking for a PoC**: 100 agent spaces / region, 3 concurrent investigations / space (adjustable), 10 concurrent on-demand invocations / space.
- **Cross-region monitoring is implicit** — one Agent Space in us-west-2 can discover resources across every region of the associated account.
- **EKS auth mode of `k8-1` is `API_AND_CONFIG_MAP`** — the EKS API path is enabled, prerequisite for the access entry approach.

## Next iterations (not yet implemented)

### Primary focus: guardrail-aware HyperPod skills

The experiment's current direction is investing in the **agent's intelligence** rather than in custom notification plumbing or auto-execution. The trigger pipeline (EventBridge → Lambda → webhook, drop `Info` only) is intentionally left as-is. The work goes into the skills the agent loads after the webhook fires, so investigations produce better triage decisions and higher-quality recommendations.

The upstream `awslabs/agent-plugins` HyperPod skills aren't a drop-in answer because they were authored for Claude Code / Codex runtimes that can drive SSM sessions. Inside DevOps Agent's permission guardrail, most of their procedures aren't executable. The work below is rewriting them with what *is* reachable: SageMaker control-plane APIs, EKS kubectl, CloudWatch Logs/metrics, CloudTrail. Where the upstream skill needed shell, the rewrite splits into "agent reads a proxy signal" (e.g. HMA's CloudWatch log stream for Xid evidence) and "agent recommends the customer run this SSM command and paste the output back."

Three skill layers planned:

1. **Triage skill** (`agent_types: ["INCIDENT_TRIAGE"]`). Decides per-incident:
   - Skip when HyperPod is already auto-resolving (HMA classification + `NodeRecovery=Automatic` + replacement event sequence in `ListClusterEvents` → cluster is healing itself, no new information from a full investigation).
   - Skip when `Investigation Linked` already happened.
   - Proceed otherwise — especially when no HMA classification matches the event, when `NodeRecovery=None`, when multiple replacements happen in a short window, or when cluster status is `Failed`/`RollingBack`.
   - Highest leverage on noise and investigation-quota burn.

2. **Per-failure-mode investigation skills** (`agent_types: ["INCIDENT_RCA"]`), each rewritten from an upstream skill with three structural changes:
   - Every upstream "Suggested command" block reframed as either an in-guardrail agent action (SageMaker API / kubectl / CloudWatch query) OR an explicit customer recommendation with the exact SSM command to confirm.
   - A proxy-signal map for each on-node truth the upstream skill relied on. Example: for Xid evidence, the agent reads the `SagemakerHealthMonitoringAgent/<group>/<instance>` CloudWatch log stream instead of `dmesg`. For DCGM, it reads HMA's classification rather than running `dcgmi`.
   - A required confidence section in every RCA output: which conclusions are direct observation vs. proxy inference, what the agent could not verify, and what the customer would need to run to close the gap.

3. **Recommendation-quality skill** (`agent_types: ["INCIDENT_MITIGATION"]`). Standardized mitigation-plan template so every recommendation includes: the precise action, the API/command, safe-state preconditions, rollback, and success criteria. Borrows the discipline of the upstream skills' Suggested-command blocks without requiring agent-side execution.

Build order TBD — likely triage first (smallest, validates the description-matching logic for `INCIDENT_TRIAGE`-typed skills), then port one investigation skill (node-debugger or nccl), then layer the mitigation skill on top.

### Other follow-ups (lower priority)

- **Slack channel for live investigation updates** — built-in Slack integration; paused on workspace 3P approval.
- **Investigation lifecycle EventBridge rule** — fan out `aws.aidevops` events to SNS / email / Lambda. Not built; not blocking.
- **External diagnostic collector** (read [SSM access — the permission guardrail is a hard ceiling](#ssm-access--the-permission-guardrail-is-a-hard-ceiling) above). Would side-load on-node truth into CloudWatch Logs or S3. Only worth building if the proxy-signal map in the rewritten investigation skills hits a real wall.
- **Slurm path** — same shape, but using SSM-based access to the head node instead of EKS access entries. SSM unavailable from the agent means the proxy-signal map matters even more for Slurm.
