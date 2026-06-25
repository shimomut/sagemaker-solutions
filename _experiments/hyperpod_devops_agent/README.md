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
│   └── hyperpod-investigation/
│       ├── SKILL.md           - frontmatter + decision tree the agent loads
│       └── references/        - per-event runbooks + HyperPod resource map
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

# Step 5 - Upload the HyperPod knowledge skill (so the agent knows what HyperPod is)
make upload-skill                                  # zips skills/hyperpod-investigation/ -> create-asset
make list-skills                                   # show all skills + their type (USER vs LEARNED)
# To remove: make delete-skill

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

## Knowledge: the `hyperpod-investigation` skill

DevOps Agent does not understand HyperPod out of the box — a HyperPod cluster is "a SageMaker resource" to its topology engine, not a composition of EKS + EC2 + FSx + lifecycle scripts. The `skills/hyperpod-investigation/` directory teaches it that mapping.

Structure:

```
skills/hyperpod-investigation/
├── SKILL.md                            # decision tree the agent reads first
└── references/
    ├── hyperpod-resource-map.md        # HyperPod -> EKS/EC2/FSx/VPC + API map
    ├── runbook-node-health.md          # per-event procedure
    ├── runbook-cluster-state.md
    └── runbook-cluster-event.md
```

The skill's frontmatter `description:` is what makes the agent decide to load it — it lists triggering keywords (`HyperPod`, `aws.sagemaker`, the three EventBridge detail-types, common failure modes) so the description-match step lights up for any incident originating from our webhook bridge.

`make upload-skill` zips the directory and calls `aws devops-agent create-asset --asset-type skill`. Re-running calls `update-asset` instead of creating duplicates. To author additional skills, drop a new directory under `skills/` and run `SKILL_DIR=skills/my-skill make upload-skill`.

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
| **Skills** (asset API) | Inside the agent | Yes — `skills/hyperpod-investigation/` teaches the agent the HyperPod resource model and per-event runbooks. |

Confirmed for our environment:

- **us-west-2 is a supported Agent Space region** (`aidevops.us-west-2.amazonaws.com`).
- **Quotas are non-blocking for a PoC**: 100 agent spaces / region, 3 concurrent investigations / space (adjustable), 10 concurrent on-demand invocations / space.
- **Cross-region monitoring is implicit** — one Agent Space in us-west-2 can discover resources across every region of the associated account.
- **EKS auth mode of `k8-1` is `API_AND_CONFIG_MAP`** — the EKS API path is enabled, prerequisite for the access entry approach.

## Next iterations (not yet implemented)

1. **Slack channel for live investigation updates** — configure the built-in Slack integration in the Agent Space console.
2. **Investigation lifecycle EventBridge rule** — fan out `aws.aidevops` events to SNS/email/Lambda for offline review.
3. **More skills** — current skill covers the three HyperPod EventBridge detail-types and the resource map. Future additions: NCCL/EFA triage, FSx Lustre throughput, Karpenter scaling issues.
4. **Slurm path** — same shape, but using SSM-based access to the head node instead of EKS access entries.
