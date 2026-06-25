# HyperPod x AWS DevOps Agent — experiment

Wire SageMaker HyperPod (EKS-orchestrated cluster `k8-1`) into [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/) and see what the agent does with it out of the box.

This iteration is a **minimal end-to-end loop**: stand up an Agent Space, give it read-only access to the underlying EKS cluster, and run a manual investigation from the web app. No custom EventBridge bridges, no remediation Lambdas, no auto-triggering — that comes later, once we've seen what the agent produces unprompted.

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
│   └── 99_teardown.sh
└── .state.json              - written by setup, read by teardown (git-ignored)
```

## Prerequisites

- AWS CLI v2 configured for the target account.
- HyperPod cluster `k8-1` in `us-west-2` (account 842413447717) — already exists.
- Permission to create IAM roles and call `devops-agent:*` + `eks:CreateAccessEntry`.

## Quick start

```bash
make help                    # show every target
make extract-docs            # one-time: build searchable .txt from the PDFs

make check-aws               # whoami + caller identity
make check-cluster           # confirms HyperPod + EKS auth mode
make config                  # show resolved config (region, role names, ...)

make setup                   # full setup: iam-roles -> agent-space -> eks-access
make status                  # print state file + Operator web app URL

# Then, in the AWS console, open the Operator web app and start a manual
# investigation like "Investigate node health on HyperPod cluster k8-1".

make teardown                # remove EKS access entry, agent space, IAM roles
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
| 1 | IAM role `DevOpsAgentRole-AgentSpace` | Assumed by `aidevops.amazonaws.com` to read AWS resources during investigations. Attaches managed policy `AIDevOpsAgentAccessPolicy` + an inline policy allowing the Resource Explorer service-linked role to be created. Trust is scoped to this account's `agentspace/*`. |
| 2 | IAM role `DevOpsAgentRole-WebappAdmin` | Backs the Operator web app. Attaches managed policy `AIDevOpsOperatorAppAccessPolicy`. |
| 3 | Agent Space `hyperpod-devops-agent-poc` (in `us-west-2`) | The logical container for accounts, integrations, knowledge. |
| 4 | Primary AWS account association (`accountType=monitor`) | Turns on topology discovery across all regions of the account. |
| 5 | Operator web app (auth flow `iam`) | UI entry point at `https://us-west-2.console.aws.amazon.com/aidevops/...`. |
| 6 | EKS access entry on `sagemaker-k8-1-1bd2626f-eks` | Grants the Agent Space monitoring role read-only kubectl via the AWS-managed `AmazonAIOpsAssistantPolicy` access policy, cluster scope. |

The agent cannot create, modify, or delete K8s resources — `AmazonAIOpsAssistantPolicy` is read-only (describe, get pod logs, list events, check node health, etc.).

## What `make setup` does NOT create

- No Lambdas, EventBridge rules, SES, or Slack/PagerDuty integrations.
- No webhooks (so investigations don't auto-start from HyperPod events yet).
- No skills, custom agents, or instructions uploaded to the Agent Space.
- No changes to the HyperPod cluster or its data plane.

These are intentionally deferred — they belong to follow-up iterations once we've seen baseline behavior.

## Findings from the DevOps Agent docs (anchor for design)

DevOps Agent is organized around **Agent Spaces** (logical containers for accounts, integrations, knowledge, permissions). Production operations breaks into three capabilities:

- **Autonomous incident response** — kicked off by alerts/tickets/webhooks. Triages (link / skip / proceed), correlates telemetry across the topology, identifies root cause, proposes a mitigation plan.
- **Proactive incident prevention** — weekly cross-incident analysis that surfaces recommendations across observability / infra / governance / code.
- **On-demand DevOps tasks** — natural-language chat over the topology.

Integration surfaces relevant to HyperPod:

| Surface | Direction | Use for HyperPod |
| --- | --- | --- |
| **EKS access entry** (this PoC) | Pull | Read-only kubectl against the underlying EKS cluster. Agent describes resources, retrieves pod logs, inspects cluster events, checks node health. |
| **Webhooks** (generic, HMAC-signed) | _Into_ the agent | Trigger an investigation from any HyperPod signal (cluster events, K8s events, custom alarms). Not used in this iteration. |
| **EventBridge** events `source: aws.aidevops` | _From_ the agent | React to investigation lifecycle (Created / In Progress / Completed / Failed / Timed Out / Cancelled / Skipped / Linked). Not used in this iteration. |
| **Skills** (modular instruction sets) | Inside the agent | Encode HyperPod-specific runbooks (node replacement, FSx checks, NCCL triage). Authored via `aws devops-agent create-asset --asset-type skill`. Not used in this iteration. |

Confirmed for our environment:

- **us-west-2 is a supported Agent Space region** (`aidevops.us-west-2.amazonaws.com`).
- **Quotas are non-blocking for a PoC**: 100 agent spaces / region, 3 concurrent investigations / space (adjustable), 10 concurrent on-demand invocations / space.
- **Cross-region monitoring is implicit** — one Agent Space in us-west-2 can discover resources across every region of the associated account.
- **EKS auth mode of `k8-1` is `API_AND_CONFIG_MAP`** — the EKS API path is enabled, which is the prerequisite for the access entry approach.

## Next iterations (not yet implemented)

1. **Webhook trigger**: EventBridge → Lambda forwarder that shapes a HyperPod node-health event into a generic webhook call so investigations auto-start.
2. **Lifecycle observation**: a Lambda subscribed to `source: aws.aidevops` lifecycle events that logs every investigation to CloudWatch.
3. **HyperPod-specific skill**: a `SKILL.md` checked into this repo and uploaded via the Asset API, encoding our node-replacement and NCCL-triage runbooks.
4. **Slurm path**: same shape, but using SSM-based access to the head node instead of EKS access entries.
