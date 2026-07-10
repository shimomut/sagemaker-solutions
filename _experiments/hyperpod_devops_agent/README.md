# HyperPod x AWS DevOps Agent

Wire any SageMaker HyperPod cluster into [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/) so cluster issues are auto-detected, investigated by the agent, classified against HyperPod's built-in resiliency behavior, and surfaced via email (and DevOps Agent's own notification channels).

## What this delivers

Four stacked pieces:

1. **Agent Space + EKS access** — gives the DevOps Agent read-only `kubectl` against the underlying EKS cluster (auto-discovered from the HyperPod cluster's `Orchestrator.Eks.ClusterArn`) and a console where investigations land. Slurm clusters skip the EKS step automatically.
2. **Webhook bridge** — CloudFormation stack with an EventBridge rule on `aws.sagemaker` HyperPod events and a Lambda that POSTs them to the DevOps Agent generic webhook. Supports a cluster allowlist so customers with multiple HyperPod clusters can scope which ones trigger investigations.
3. **Two complementary skills** that classify each event against HyperPod's built-in resiliency model (read [docs/hyperpod-mental-model.md](../../docs/hyperpod-mental-model.md)):
   - **`hyperpod-incident-triage`** (INCIDENT_TRIAGE) — runs at the triage stage to decide `LINKED` / `SKIPPED` / `PROCEED`, keeping different fault types on the same instance group as separate investigations (the default correlator merges them) and preventing periodic-audit re-investigation of an unchanged cluster. An earlier algorithmic version (v0.6.1) did not take effect; **v0.7.0 rewrites it as concise declarative rules** in the style of AWS's own sample triage skill. See [Triage-skill correlation: status and how to author it](#triage-skill-correlation-status-and-how-to-author-it) and verify behavior empirically after deploy.
   - **`hyperpod-incident-rca`** (INCIDENT_RCA) — runs after triage produces PROCEED. Reads `describe-cluster`, `list-cluster-nodes`, `list-cluster-events`, and HMA CloudWatch streams; reconstructs a timeline; classifies as Suppress / Monitor / Escalate / Resolved against time budgets and recurrence statistics. Produces a human-readable verdict report with recommended operator actions.
4. **Periodic-audit stack** — CloudFormation stack: `AWS::Scheduler::Schedule` (every 15 min) → Lambda → HMAC-signed POST to the same webhook. Fires the skill in audit mode so open fault chains get re-checked (Goal 1: monitor duration, emit closure notification on silent-success recovery, escalate stuck chains). See [Two operational goals beyond single-shot investigations](#two-operational-goals-beyond-single-shot-investigations) for why this couldn't use DevOps Agent's native scheduled triggers.
5. **Email notifier** — CloudFormation stack: EventBridge rule on `aws.aidevops` `Investigation Completed` → Lambda → SES email. Composes the HTML body directly from journal records (`get_backlog_task` + `list_journal_records`) so it's resilient to RCA-skill drift. Dedups via an S3 marker bucket (`hyperpod-devops-agent-email-markers-<account>-<region>`) keyed by `execution_id`, so DevOps Agent's frequent re-emission of the same `Investigation Completed` event doesn't produce duplicate emails. Filters `Suppress` verdicts and zero-finding investigations so periodic audits on a healthy cluster don't produce noise. `FORCE_SEND=true` on the CFN stack bypasses every filter for debugging.

Slack notifications can be added later (paused on workspace 3P approval) via DevOps Agent's built-in Slack integration or via a sibling stack that listens on the same `aws.aidevops` event stream.

## Layout

```
.
├── Makefile                 - make targets for every step below
├── README.md                - this file
├── docs/                    - DevOps Agent UG + API ref PDFs (git-ignored) + extracted .txt
│   └── devops-agent-mental-model.md  - undocumented DevOps Agent behaviors we discovered (read before changing skills/bridge/audit)
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
├── periodic_audit/
│   ├── template.yaml        - CloudFormation: EventBridge Scheduler + Lambda (Goal 1 fallback)
│   └── lambda_function.py   - Synthesizes periodic-audit webhook event, HMAC-signs, POSTs
├── skills/
│   ├── hyperpod-incident-triage/   - INCIDENT_TRIAGE skill (decides LINKED/SKIPPED/PROCEED)
│   ├── hyperpod-incident-rca/      - INCIDENT_RCA skill (full investigation + verdict)
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
│   ├── 12_deploy_periodic_audit.sh
│   ├── 13_delete_periodic_audit.sh
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

# Step 4 - Upload both skills (triage runs first, RCA runs after PROCEED)
SKILL_DIR=skills/hyperpod-incident-triage make upload-skill
SKILL_DIR=skills/hyperpod-incident-rca   make upload-skill

# Step 5 - Optionally import a curated subset of upstream skills as reference
make import-upstream-skills                        # see "Skill curation" below for defaults
make list-skills

# Step 6 - Periodic audit (Goal 1 + Kubernetes-state checks)
make deploy-periodic-audit       # EB Scheduler -> Lambda -> webhook (audit mode every 15 min)
# Optional overrides for the Kubernetes-state checks (defaults shown):
#   K8S_CHECKS_ENABLED=true CRASHLOOP_HOURS_THRESHOLD=4 \
#   NOT_READY_NODE_PERCENT_THRESHOLD=10 NOT_READY_DURATION_MINUTES=15 \
#   IGNORE_NAMESPACES='kube-public,kube-node-lease' \
#   SYSTEM_NAMESPACES='kube-system,aws-hyperpod,amazon-cloudwatch' \
#       make deploy-periodic-audit
make audit-logs                  # tail the audit Lambda's CloudWatch Logs (Ctrl-C to stop)
make audit-test                  # invoke the audit Lambda once manually (don't wait 15 min)

# Step 7 - Email notifications (SES sender must be verified in REGION)
EMAIL_SENDER=alerts@example.com \
EMAIL_RECIPIENTS=oncall@example.com,team@example.com \
    make deploy-email-notifier

# Teardown
make teardown                # email-notifier -> periodic-audit -> bridge -> EKS entry -> agent space + eventChannel -> IAM roles stack
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

1. **Our two skills**:
   - **`hyperpod-incident-triage`** (INCIDENT_TRIAGE) — runs at the triage stage and decides LINKED / SKIPPED / PROCEED. See [skills/hyperpod-incident-triage/SKILL.md](skills/hyperpod-incident-triage/SKILL.md). Why it exists: the platform's default correlator merges cross-fault-type events on the same instance group, which causes information loss; this skill instructs the triage agent to keep them separate. Authoring matters — an earlier algorithmic version didn't take effect; v0.7.0 uses concise declarative rules. See [Triage-skill correlation: status and how to author it](#triage-skill-correlation-status-and-how-to-author-it).
   - **`hyperpod-incident-rca`** (INCIDENT_RCA) — runs after the triage skill produces PROCEED. Reads `describe-cluster`, `list-cluster-nodes`, `list-cluster-events`, and HMA CloudWatch streams; reconstructs a timeline; classifies as Suppress / Monitor / Escalate against time budgets derived from the [HyperPod mental model](../../docs/hyperpod-mental-model.md). Bundles the mental-model doc as a reference. See [skills/hyperpod-incident-rca/SKILL.md](skills/hyperpod-incident-rca/SKILL.md).

2. **Curated upstream skills from [awslabs/agent-plugins](https://github.com/awslabs/agent-plugins)** — supporting reference. `make import-upstream-skills` imports a **curated subset** of the `hyperpod-*` skills (see "Skill curation" below). Use the `SKILLS=...` env var to import a different subset. Subsequent runs `git pull` upstream and re-upload.

### Triage-skill correlation: status and how to author it

Custom triage correlation **is supported** by DevOps Agent. Per the UG
([Autonomous incident response](https://docs.aws.amazon.com/devopsagent/latest/userguide/production-operations-autonomous-incident-response.html)):
you can "provide custom correlation rules by creating a DevOps Agent Skill
containing your correlation logic and associating it with the triage stage," and
skip criteria are likewise defined by an `INCIDENT_TRIAGE` skill. AWS ships a
sample (`sample-skip-scheduled-maintenance`) that is ~5 lines of plain-English
skip rules.

**What we observed before the rewrite:** an earlier version of
`hyperpod-incident-triage` (v0.6.1) did **not** take effect — two
different-fault-type events on the same instance group were still merged by the
default correlator (the second task went `LINKED` to the first within ~30s, with
no triage execution visibly running our skill). The skill was uploaded correctly
(one ACTIVE `INCIDENT_TRIAGE` asset per space, right metadata, no duplicates), so
this was **not** a deployment/config issue.

**Most likely cause — skill authoring, not a platform ceiling.** That version
was ~400 lines of algorithmic pseudo-code (signature-set computation, multi-phase
steps, `list-backlog-tasks` lookups). The triage agent consults a skill as
natural-language *instructions*, not as code it executes deterministically — so
concise declarative rules (like the AWS sample) are followed far more reliably
than a long algorithm. **v0.7.0 rewrites the skill in that concise declarative
style** ("link only when the same fault on the same component recurs; keep
different fault types on the same instance group separate; …"). Re-test after
deploying to confirm the correlation now behaves as intended.

**How to author an `INCIDENT_TRIAGE` skill that takes effect (lessons learned):**

- State a **few plain rules** the agent should follow (link/skip/proceed
  *criteria*), not an algorithm to run. Mirror the tone of the AWS sample.
- Describe **identity in words** ("same instance group AND same fault text"),
  not as data structures the agent must build and compare.
- Keep it short. Long, procedural skills read as reference material the agent may
  or may not apply, rather than triage directives.

**Observability caveat:** there is no customer-facing log/API that reports the
triage decision or which skill produced it. The only signals are the EventBridge
`Investigation Linked` / `Skipped` events and `list-executions`. Verify behavior
empirically (fire correlated synthetic events and observe the resulting
LINK/SKIP/PROCEED), as described in this repo's testing notes.

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

1. **Email (via SES)** — deployed by `make deploy-email-notifier`. EventBridge rule on `source: aws.aidevops`, detail-type prefix `Investigation` → Lambda → `ses:SendEmail` to the configured recipients. By default sends on `Investigation Completed` only (one email per lifecycle); `Investigation Created` / `Investigation Updated` / `Investigation Linked` events are ignored to avoid mid-flight spam. Override with `EMAIL_DETAIL_TYPES`.
   - **Body composition reads the full journal.** The Lambda calls `aidevops:GetBacklogTask` + `aidevops:ListJournalRecords` and renders symptoms, findings, and investigation_gaps directly. It does not rely on parsing a single verdict-title string, so it degrades gracefully when the RCA skill drifts.
   - **Dedup is S3-marker-based, keyed by `execution_id`.** Before every send the Lambda does a `HeadObject` against `s3://hyperpod-devops-agent-email-markers-<account>-<region>/emailed/<execution_id>`. If the marker exists, the event is dropped without any DevOps Agent API calls. The marker is written *after* `ses:SendEmail` returns a MessageId. This defends against DevOps Agent re-emitting `Investigation Completed` for the same execution — observed empirically, and the platform gives no configurable knob to prevent it. Marker objects auto-expire (30 days by default; `MarkerExpirationDays` CFN parameter).
   - **Skip filters (in order):** detail-type allowlist → S3 marker → Suppress-verdict detection (checks `Triage verdict: Suppress` prefix on any symptom title, plus a `Verdict: Suppress` regex fallback on the first symptom's description) → no-actionable-content (zero findings AND no verdict symptom). `FORCE_SEND=true` on the stack bypasses all of them.
   - SES sender must be verified in `$REGION`. If SES is in sandbox mode, every recipient must also be verified.
   - The IAM policy on the Lambda restricts `ses:SendEmail` to the configured `EMAIL_SENDER` via the `ses:FromAddress` condition. S3 read/write is scoped to the marker bucket only.
2. **DevOps Agent web app** — every investigation is visible at the Agent Space console URL printed by `make status`.
3. **Slack / ServiceNow / PagerDuty / Microsoft Teams** — configure once in the Agent Space console (paused on workspace 3P approval for the originating project). The same `aws.aidevops` event stream the email notifier listens on is available for any additional fan-out.

## Findings from the DevOps Agent docs (anchor for design)

DevOps Agent is **alert-driven, not polling**. Investigations only run when something triggers them: a webhook, a ticket integration, a third-party SaaS hook, or a manual click. Out of the box it has no concept of "watch HyperPod" — that's why the webhook bridge exists.

Integration surfaces relevant to HyperPod:

| Surface | Direction | Used here? |
| --- | --- | --- |
| **EKS access entry** | Pull | Yes — read-only `kubectl` against the underlying EKS cluster. |
| **Generic webhook** (HMAC) | Into the agent | Yes — webhook bridge for live HyperPod events + periodic-audit Lambda for scheduled audit-mode investigations. |
| **EventBridge `aws.aidevops`** | From the agent | Yes — the email notifier listens on `Investigation` detail-types and sends SES email. |
| **`AWS::Scheduler::Schedule`** → webhook | Into the agent (scheduled) | Yes — periodic-audit stack fires the skill in audit mode every 15 minutes. Replaces the native `devops-agent create-trigger` API path, which only supports `actionType: "create:task"` and produces an agent runtime without AWS API access or user-skill mounts. |
| **Skills** (asset API) | Inside the agent | Yes — our `hyperpod-incident-triage` and `hyperpod-incident-rca` skills run at the triage and RCA stages respectively; a curated subset of upstream `hyperpod-*` skills is imported as supporting reference. |

Operating notes:

- **Agent Space region** — Agent Space is available in a fixed set of regions; check `aidevops.<region>.amazonaws.com` resolves before running. The chosen region applies to the Agent Space resource itself; cross-region monitoring is implicit (one Agent Space discovers resources across every region of the associated account).
- **Quotas (per the UG)**: 100 agent spaces / region, 3 concurrent investigations / space (adjustable), 10 concurrent on-demand invocations / space.
- **EKS access prerequisite** — the underlying EKS cluster's `authenticationMode` must be `API` or `API_AND_CONFIG_MAP`. The setup script verifies this and aborts with the corrective `update-cluster-config` command if not.

## The `hyperpod-incident-*` skills — triage + RCA

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

### First symptom must be the verdict symptom (skill ↔ notifier contract)

The email notifier's subject-line headline and the Layer-4 platform verdict-title dedup both key off the FIRST symptom record having a title that begins with `Triage verdict:`. A descriptive first-symptom title (e.g. `"worker1 lifecycle script execution failures on k8-1"`) breaks both — the notifier falls back to the raw task title and dedup can't recognize the signature set.

The RCA skill's [CRITICAL: the FIRST symptom is the verdict symptom](skills/hyperpod-incident-rca/SKILL.md) section pins this down with four few-shot examples (Escalate recurring, Escalate coordinated LCS, Monitor first-attempt, Suppress audit) and an anti-example. The notifier still degrades gracefully — it will pick the first symptom's title or the task title if no verdict-prefixed symptom exists — but dedup will miss and downstream automation loses the verdict category.

## Two operational goals beyond single-shot investigations

Webhook-triggered investigations are single-shot: the agent writes a report and exits. Without something more, that misses two operationally critical patterns:

1. **Goal 1 — monitor incident duration + emit a closure notification.** When a `Monitor` verdict is followed by silent successful recovery (HyperPod replaces the node cleanly and only `Info`-level events get emitted), the customer never gets a "resolved" notification. Worse: when an auto-recovery silently fails or stalls past its expected window, no follow-up event fires either.
2. **Goal 2 — detect statistically recurring patterns.** Each occurrence may auto-resolve correctly, but a recurring Xid signature across 3+ replacements on the same IG in a week is a hardware/capacity-pool problem auto-recovery can't fix. No single-incident view surfaces this.

Both are now solved. Goal 2 by a skill change. Goal 1 by a new CloudFormation stack.

### Goal 2 — sliding-window classification inside the skill

Phase 2b of the skill computes recurrence statistics over the 7-day `list-cluster-events` window, and Phase 3 rules 6-8 fire on threshold crossings:

- `xid_signature_count_7d[(<xid>, <ig>)] ≥ 3` → `Escalate — recurring hardware fault pattern`
- `replacements_24h_total ≥ 5` → `Escalate — fleet-wide instability`
- `replacements_7d_by_group[<ig>] ≥ 5` → `Escalate — instance-group instability`

Verified end-to-end: after three injected Xid 74 faults on `worker2`, the skill emitted `Escalate — recurring hardware fault pattern` with three competing hypotheses (`statistical hardware`, `infrastructure path`, `software/workload`), each marked `[unverified]`, plus the GPU-UUID SSM check as an `investigation_gap` for the operator to run.

### Goal 1 — periodic-audit stack (`make deploy-periodic-audit`)

Native DevOps Agent triggers were tried first and **ruled out**. The fallback is a small CFN stack: `AWS::Scheduler::Schedule` → Lambda → HMAC-signed POST to the same webhook the bridge uses. The audit fires every 15 minutes; the `hyperpod-incident-rca` skill processes both audit-mode and incident-mode triggers; verdicts go through the existing email path. The `hyperpod-incident-triage` skill runs first to decide LINKED/SKIPPED/PROCEED — its effectiveness depends on authoring style; see [Triage-skill correlation: status and how to author it](#triage-skill-correlation-status-and-how-to-author-it).

#### Kubernetes-state checks in audit mode

Beyond HyperPod's own event stream, the audit-mode RCA can inspect Pod and Node state via the EKS access entry the foundation stack already grants. Two rules, both gated behind `K8sChecksEnabled=true` (default):

| Rule | Escalates when | Configurable via |
|---|---|---|
| **CrashLoopBackOff duration** | Any Pod is in CrashLoopBackOff for longer than the threshold | `CrashLoopHoursThreshold` (default 4 h) |
| **NotReady node percentage** | ≥ percent of nodes have been NotReady for ≥ duration | `NotReadyNodePercentThreshold` (default 10) + `NotReadyDurationMinutes` (default 15) |

Namespace handling uses **two plain lists**, no DSL. The Lambda validates at cold start that they do not overlap; overlapping deployments fail the audit invocation with a clear error message.

| Parameter | Default | Semantics |
|---|---|---|
| `IgnoreNamespaces` | `kube-public,kube-node-lease` | Pods here are skipped entirely — no verdict, no `kubectl` inspection. |
| `SystemNamespaces` | `kube-system,aws-hyperpod,amazon-cloudwatch` | CrashLoop verdicts on these are tagged `system-workload`. Downstream email routing can page the platform team differently from customer-workload verdicts. |
| everything else | — | Tagged `customer-workload`. |

Design rationale — why two lists instead of a `NamespaceScope="pattern=treatment,..."` DSL: the skill executes classification via **plain set-membership lookups on already-resolved lists**, not by parsing a DSL at run time. That matches the same principle behind the RCA skill's signature-string design — push structure into the Lambda, keep the skill's job to English-language reasoning over already-structured input. An earlier iteration of the RCA skill used regex-driven category enums and produced inconsistent verdicts; the same shape risk applies to any run-time DSL parsing.

The trigger payload's `data.metadata.k8sChecks` block carries the resolved lists + thresholds. The skill's [Phase 3d](skills/hyperpod-incident-rca/SKILL.md) reads them, no hardcoded values. Override any parameter via env var when running `make deploy-periodic-audit` (see Quick start step 6).

**Why the native path doesn't work (recorded so we don't redo this):**

`aws devops-agent create-trigger` accepts `--type TIME_BASED` triggers with `schedule={expression=rate(...)}`, but the `--action` field only accepts `{"actionType":"create:task","task":{"agent":"custom:<assetId>"}}`. Tested 2026-06-29:

- The trigger does fire on its `rate(15 minutes)` schedule (confirmed in `list-backlog-tasks`).
- The fire produces a task of `taskType=CUSTOM`, not `INVESTIGATION`.
- A `CUSTOM` task runs in a different agent runtime than an investigation: it has **no AWS API executor** wired up (so `sagemaker:list-clusters` etc. is unreachable), and **user skills are not mounted on its filesystem** (only `/skills/system/{create-artifact,feedback,recommendations}/`). The skill's `fs_read` on `/skills/references/hyperpod-mental-model.md` fails with `FileNotFoundError`.
- `actionType: "INVESTIGATION"` is rejected: *"action is not supported today; supported actionType values: create:task; supported agent values: custom:<assetId>"* — quoted verbatim from the API error. The DevOps Agent chat assistant suggested INVESTIGATION as an actionType; that's incorrect.

So the native trigger fires but creates an agent invocation that can't run the audit. The EB Scheduler + Lambda fallback synthesizes a webhook event and routes through the working investigation path. Cost: one extra investigation every 15 minutes; on a healthy cluster, the skill lands on `Suppress — periodic audit, no open incidents` (rule 1) and the email notifier's Suppress-verdict detection drops it. No idle-cluster email noise.

When AWS extends the trigger API to accept `actionType: "create:investigation"` or equivalent (the API error wording — *"supported actionType values: create:task"* — implies this list is expected to grow), we can replace the EB Scheduler stack with a single `aws devops-agent create-trigger` call. The skill itself doesn't change.

#### Avoiding duplicate-Escalate spam: the 5-layer dedup architecture

A naive periodic audit re-Escalates the same evidence every 15 minutes for the full 7-day `list-cluster-events` window — ~672 duplicate emails per stale event burst. Five layers prevent this:

| Layer | Mechanism | Where | Window |
|---|---|---|---|
| 1. **Bridge Info-filter** | Webhook bridge drops `EventLevel=Info` events | Lambda before webhook POST | Instant |
| 2. **Platform task dedup (audit event)** | DevOps Agent's triage stage analyzes the incoming task alongside active investigations within a look-back window. Uses AI-powered analysis of component similarity, region, and timing to decide LINK / SKIP / PROCEED. | Inside DevOps Agent | ~20 min per the UG ("typically 20 minutes"; we observed up to ~30 min) — the window is **not directly configurable**, but the LINK/SKIP decision can be steered by a custom `INCIDENT_TRIAGE` skill ([authoring notes](#triage-skill-correlation-status-and-how-to-author-it)) |
| 3. **Skill rule 3** | Skill emits `Suppress — periodic audit, evidence is stale` when the current signature set equals the prior audit's signature set AND no new fault event since the prior audit's `most_recent_event_at` | Inside the skill | 20 min — 7 days |
| 4. **Platform verdict-title dedup** | Verdict title includes a `(IG:category:key, ...)` signature set so identical sets produce identical titles → platform-triage links | Inside DevOps Agent, second layer | ~20 min |
| 5. **Email notifier prefix-skip** | Email notifier filters `Triage verdict: Suppress —*` from email delivery | After verdict produced | After Phase 4 |

Important properties:

- **A new fault type during a stale window re-notifies.** The signature set is keyed on `(InstanceGroup, Xid-signature)` pairs. A new Xid type on the same IG, or the same Xid spreading to a new IG, produces a different set → different verdict title → breaks layer 4's dedup AND breaks layer 3's "set unchanged" check. The operator gets the new verdict.
- **An existing-but-new occurrence of the same `(IG, Xid)` re-notifies.** Layer 3 also checks `current_most_recent_event_at != prior_most_recent_event_at`. A genuinely new event (even of an already-known signature) updates the timestamp and breaks suppression. Operators are kept current on recurrence frequency.
- **Stable audit-event titles** (`HyperPod periodic audit: <cluster>`) are used in the bridge payload so layer 2 (platform dedup) reliably absorbs back-to-back audits without semantic computation. Variations were tried (`@ <timestamp>` suffix) and rejected as fragile — the platform's dedup is semantic, not exact-match.
- **The platform's ~20-min triage look-back window is not a configurable knob**, but per the UG's "Incident triage" section a custom `agent_types: ["INCIDENT_TRIAGE"]` skill can steer the LINK/SKIP decision — that is what `hyperpod-incident-triage` does. Effectiveness depends on authoring the skill as concise declarative rules (an earlier algorithmic version didn't take effect; see [Triage-skill correlation: status and how to author it](#triage-skill-correlation-status-and-how-to-author-it)). Layers 3–5 (skill-emitted `Suppress`, verdict-title dedup, email prefix-skip) function independently and carry the anti-spam load regardless.

## Follow-ups (not yet built)

- **CloudWatch Logs subscription filter on the HMA stream as an additional trigger source.** Faster + more granular than the SageMaker EventBridge `Cluster Event` Warn — catches HMA detections that don't always surface as control-plane events. Lets us filter on specific Xid codes / ECC counts / LCS-script failures. Worth doing if any future investigation reveals a missed signal.
- **Per-incident scheduled re-check via DynamoDB + EB Scheduler.** The current periodic audit re-checks the cluster every 15 minutes regardless of incident state; a DynamoDB-backed version would re-check only when a `Monitor` row is open and would precisely time the re-check (15 min for `Monitor — first attempt`, 10 min for `Monitor — elevated`). Cleaner cost profile on quiet clusters with rare incidents, but adds DynamoDB + a separate verdict-extractor Lambda. The current always-fire audit is good enough as long as quota isn't a concern.
- **Slack channel for live investigation updates** — paused on workspace 3P approval. The email notifier's EventBridge listener is the template; a Slack notifier drops into the same `aws.aidevops` event stream.
- **External diagnostic collector** (see [SSM access — the permission guardrail is a hard ceiling](#ssm-access--the-permission-guardrail-is-a-hard-ceiling) above). Would side-load on-node truth (DCGM, EFA fabric counters, kubelet journal) into CloudWatch Logs or S3 where the guardrail can read them. Build only if a future investigation hits a wall the proxy-signal path can't reach.

7. **Per-failure-mode RCA skills** beyond `hyperpod-incident-rca` — narrower skills (NCCL hang, slow storage, lifecycle-script failure) loaded only when the RCA skill's classification matches. The current bet is that the RCA skill plus the upstream cluster/node debuggers cover most cases; branch out only if specific failure modes prove to need deeper specialization.
- **Slurm coverage validation end-to-end** — the skill is written to work for Slurm with Continuous Provisioning, but the empirical testing so far is EKS-only.
