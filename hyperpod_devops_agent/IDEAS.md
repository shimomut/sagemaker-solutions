# Ideas + Questions

Scratchpad. Just write. Title + a couple of lines + any relevant IDs.

## Weekly digest for GPU-utilization + FinOps signals

Absolute-utilization thresholds (e.g. "average <80% over 7d") don't work as incident triggers — real workloads on well-tuned code hit 60–80% MFU, exploration/notebook work hits 20–40%, so an 80% floor pages ops for every researcher iterating on a training script. This is a **FinOps / capacity-planning signal**, not an SRE-page.

Better shape: a separate **weekly digest** email (different recipients, different tone) surfacing:
- Per-IG average GPU utilization over the trailing 7d.
- Sudden utilization drop on a previously-hot IG (e.g. "worker4 was 70%+ for 6 days, now <10% for 12h and no scale-down") — that delta signal *is* actionable and could go straight into the incident channel because it points at a stuck job or GPU fault.
- Replacement counts by IG over 7d (already computed by RCA rule 8, currently only surfaced when it crosses the Escalate threshold).
- Optional: cost estimate delta week-over-week.

Prerequisites:
- **GPU metrics source.** Container Insights + DCGM exporter aren't on by default on HyperPod EKS. Verify what's in place before designing around it. Alternatively CloudWatch's built-in EC2 GPU metrics (limited) or Amazon Managed Prometheus (see next section).
- Delivery: a new EventBridge Scheduler rule at `cron(0 15 ? * MON *)` → dedicated Lambda → SES email. Skips the DevOps Agent entirely — no investigation billed, just a report. Alternatively, use DevOps Agent's native "Agents" (custom scheduled agents for weekly ops reports) if we want it inside the same product.
- Threshold-based Escalate can still live in the audit-mode skill for the specific delta case; the digest handles the ambient reporting.


## Amazon Managed Prometheus as a data source — same guardrail shape as SSM

HyperPod has an official AMP integration (kube-prometheus stack ships DCGM exporter, node-exporter, kube-state-metrics into an AMP workspace). Would be a natural data source for GPU utilization, ECC counters, NVLink stats, XID counts, EFA fabric health — the exact HMA/on-node signals the guardrail otherwise blocks us from seeing.

**Guardrail check (UG p. 358 — verified 2026-07-08)**: `AIDevOpsAgentAccessPolicy` includes `aps:Describe*` and `aps:List*` only. The data-read APIs — `aps:QueryMetrics`, `aps:GetLabels`, `aps:GetSeries`, `aps:GetMetricMetadata` — are **not** in the guardrail allowlist. Same shape as `ssm:StartSession`: adding them to the customer role has no effect because the session policy strips them.

So the agent can:
- Enumerate AMP workspaces via `aps:ListWorkspaces` / `aps:DescribeWorkspace`.
- See that HyperPod is publishing to workspace `ws-<id>`.
- **Not** query any time-series data.

Two paths forward:
1. **Ask AWS to add AMP query actions to the guardrail allowlist** (`aps:QueryMetrics`, `aps:GetLabels`, `aps:GetSeries`, `aps:GetMetricMetadata`). This is a much narrower and more defensible ask than the SSM one — read-only, scoped by workspace ARN, no on-node blast radius, no interactive shell. Bundle it with the SSM feedback item.
2. **AMP → CloudWatch bridge.** Amazon Managed Grafana / AMP alerts can already fan out to SNS. Route them through EventBridge → our webhook bridge → investigation, same shape as the SageMaker `Cluster Event` stream. Doesn't get us ad-hoc query capability during investigations, but does unlock threshold-based triggers on Prometheus metrics (per-Xid-code counts, per-GPU thermal alerts, EFA error rate) that the SageMaker EventBridge stream doesn't expose. The RCA skill would still be reasoning from HMA CloudWatch streams for post-trigger context, not from the raw Prometheus data.

Path 2 is buildable today and complements Goal 2's recurrence detection with sharper trigger signals. Path 1 is the durable fix. File the guardrail-expansion feedback either way.


## CloudWatch Metrics as a data source — already inside the guardrail

Same purpose as the AMP-as-data-source idea above (GPU utilization, hardware
health signals for the weekly digest and for sharper triggers), but **more
realistic**, because the permission story is the exact opposite of AMP's.

**Guardrail check (UG p. 359–360 — verified 2026-07-10)**: CloudWatch
metric-read actions are in the **default** `AIDevOpsAgentAccessPolicy` set, not
the opt-in allowlist. The policy grants `cloudwatch:GetMetricData`,
`cloudwatch:GetMetricStatistics`, `cloudwatch:GetMetricStream`,
`cloudwatch:ListMetrics` (`List*`), `cloudwatch:Describe*` (alarms),
`cloudwatch:GetDashboard`, `cloudwatch:GetInsightRuleReport`, and
`cloudwatch:GenerateQuery`. So unlike `aps:QueryMetrics` (guardrail-blocked) and
`ssm:StartSession` (stripped), **the agent can already query CloudWatch
time-series data ad hoc during an investigation with zero policy changes and no
guardrail-expansion ask.** This is the durable-fix state that Path 1 of the AMP
idea is still asking AWS *for* — we have it for free on the CloudWatch side.

So the permission is not the gating question. **The gating question is what's
actually published to CloudWatch for a HyperPod cluster**, and the honest answer
is "not much GPU/hardware signal by default":

- **EC2 vended metrics** (always on, `AWS/EC2`): `CPUUtilization`, network,
  EBS, status checks. No GPU utilization, no ECC/Xid/thermal — EC2 does not vend
  accelerator metrics natively. Coarse, but a *sudden CPUUtilization collapse on
  a previously-busy instance* is a usable proxy for a stalled job (complements
  the digest's delta signal without any GPU telemetry at all).
- **DevOps Agent's own vended metrics** (`AWS/AIDevOps`): operational metrics
  about the agent, not about the cluster. Not relevant here.
- **GPU/accelerator metrics require an installed publisher** and are **not on by
  default on HyperPod EKS** (same caveat as the digest section): either
  Container Insights with the accelerated-compute add-on (GPU metrics land in the
  `ContainerInsights` namespace) or the CloudWatch agent with NVIDIA support
  (`nvidia_smi_*` — utilization, memory, temperature, some ECC). DCGM's richer
  fabric/NVLink/per-Xid cardinality is really the AMP+DCGM story, not CloudWatch.

Two paths forward, mirroring the AMP section:

1. **Ad-hoc query during investigation.** Available *today* via
   `GetMetricData` / `GetMetricStatistics`. Whether it's *useful* depends
   entirely on whether the cluster has a GPU-metrics publisher installed. If it
   does, the RCA skill could pull per-instance GPU utilization / temperature /
   memory around the incident window to corroborate an HMA verdict — a strictly
   richer post-trigger context source than the HMA CloudWatch *log* streams it
   reasons from now. If it doesn't, the agent still gets EC2-level CPU/network
   as a weak proxy. No feedback item needed either way.
2. **CloudWatch alarm → SNS → EventBridge → webhook bridge** as a trigger
   source. Identical plumbing to the AMP Path 2, but sourced from CloudWatch
   alarms instead of AMP/Grafana alerts — unlocks threshold triggers on whatever
   *is* published (CPU collapse, or GPU util/thermal if a publisher exists).
   Composes with the existing `Cluster Event` stream and complements Goal 2's
   recurrence detection.

**CloudWatch vs. AMP, net:** CloudWatch is *in-guardrail today* but thin on
GPU/hardware signal unless a publisher is installed, and gets expensive at high
metric cardinality. AMP carries the rich DCGM cardinality HyperPod's official
integration already ships, but its query APIs are *outside* the guardrail
(needs the Path-1 ask). They're complementary: **prefer CloudWatch for the
buildable-now digest + trigger work, keep the AMP guardrail-expansion feedback
item for the deep per-GPU cardinality we can't get from CloudWatch.** First
concrete step for either is the same as the digest prerequisite — enumerate what
metric namespaces a real HyperPod EKS cluster actually publishes (`ListMetrics`)
before designing around any of them.


## We are not using "Agent instructions".

**Finding (2026-07-10): Agent Instructions are likely the more reliable home for
our triage rules than a Skill — but there's no API/CFN path yet, so parked.**

Difference (from the [UG](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent-agent-instructions.html)):

| | Skill (what we use now) | Agent Instructions (AGENTS.md) |
|---|---|---|
| Injection | **On demand** — the agent decides via skill-description matching; it *can skip* the content | **Always** — unconditionally injected into the system prompt every session; the agent cannot skip it |
| Triage scoping | `agent_types: ["INCIDENT_TRIAGE"]` | Scoped to the **Incident triage** managed agent specifically |
| Format | Markdown or ZIP (+ resource files) | Markdown only, no frontmatter, no resources |
| Count | Many per space | Exactly one global + one per managed agent |
| Size | — | 25 KB hard limit; ~120 lines recommended |

**Why this matters for us:** our entire triage saga was about *reliability of
invocation*. A skill fires only if the agent matches its description to the task
(exactly why v0.6.1 silently didn't fire, and why v0.7.0 "works" but still
depends on the agent choosing to apply it). **Incident-triage Agent Instructions
are guaranteed-injected every session** — strictly more reliable for the
"keep different fault types separate / concurrency-skip" rules. Our v0.7.0 skill
is already concise declarative markdown (~50 lines), so it would drop into an
AGENTS.md almost verbatim.

**Why parked, not adopted now:** there is **no `CreateAsset`/CLI/CFN path** for
Agent Instructions (the `CreateAsset` assetType enum is empty; the UG documents
only the Operator Web App Knowledge → Instructions tab: View/Edit/Upload/
Download/Delete). So they'd be a **manual, per-Agent-Space console step**, which
breaks the one-command-deploy goal. Decision: keep the automated v0.7.0 triage
Skill for now; revisit moving the rules to Incident-triage Instructions if/when
AWS exposes a programmatic path. If maximum triage reliability is needed before
then, an operator can paste the v0.7.0 rules into Knowledge → Instructions →
Incident triage manually.

Instructions are also the natural home for **always-on standing guidance** that
isn't task-specific (e.g. "this Agent Space monitors a HyperPod cluster; treat
`sagemaker:cluster` resources as HyperPod, not generic SageMaker") — a separate,
smaller use we could adopt later.
