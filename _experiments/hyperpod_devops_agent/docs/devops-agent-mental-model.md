# AWS DevOps Agent Mental Model (undocumented behaviors)

This document captures operational knowledge about **AWS DevOps Agent**
that is NOT in the product docs (UG / API reference) but that we
discovered empirically while building the HyperPod × DevOps Agent
solution. It is the DevOps-Agent counterpart to
[`hyperpod-mental-model.md`](../../../docs/hyperpod-mental-model.md):
that doc explains HyperPod; this one explains the *investigation
platform* we wire HyperPod into.

Keep this open when changing the triage skill, RCA skill, webhook
bridge, periodic-audit stack, or email notifier. Update it when you
discover a new platform behavior — especially anything that
contradicts the UG or that only surfaced through testing.

> **Status of claims.** Every section tagged **[verified]** was
> observed directly in this account (842413447717, us-west-2,
> Agent Space `hyperpod-k8-1-devops-agent`). Sections tagged
> **[inferred]** are our best explanation of observed behavior but
> weren't isolated in a controlled test. Sections tagged **[UG]** are
> documented but easy to miss.

---

## 1. The platform re-invokes a primary on every LINK — LINK is not free [verified]

**The single most important undocumented behavior.** When a new task
is LINKED to an existing primary investigation, DevOps Agent does not
just record the association and stop. It **re-invokes the primary
investigation's agent**, feeding it a message like:

> "The triage agent suspects a related investigation exists. The
> investigation (ID: …) has the title …"

Consequences we observed:

- The primary's `status` flips from `COMPLETED` back to `IN_PROGRESS`
  when a LINK arrives, and its `updatedAt` advances.
- On a periodic-audit cadence (a new audit every 15 min, each LINKing
  to the same primary), the primary can stay `IN_PROGRESS`
  effectively forever — we saw one primary stay in-progress for
  68+ minutes as successive audits kept LINKing to it.
- A LINKED task's own execution produces **zero journal records**
  (`list-journal-records` returns `[]`) — the RCA skill never runs
  for it; only the triage decision executed.

**Design implications:**

- Do NOT use LINK as a "cheap dedup" mechanism for a recurring trigger
  (like a periodic audit). LINK re-activates the primary and creates a
  feedback loop.
- To dedup a recurring audit against an in-progress one, use
  **SKIPPED**, not LINKED. SKIP terminates the incoming task cleanly
  without touching the primary.
- LINK is still correct for genuinely-duplicate *incident* events
  (same fault, same component) where you want them attached to one
  investigation and don't mind the primary re-checking.

This behavior is the reason the `hyperpod-incident-triage` skill went
through three designs (see the skill's own change-log section):
concurrency-LINK (v0.5) → signature-only (v0.6.0) → signature +
concurrency-SKIP (v0.6.1).

---

## 2. There are TWO triage layers: platform default AND custom skill [verified/UG]

DevOps Agent runs a triage stage on every incoming task **before** the
investigation (RCA) stage. Two things can decide LINK / SKIP / PROCEED:

1. **The platform's built-in AI correlator** [UG] — always present.
   Correlates by component similarity, region, and timing within a
   look-back window (the UG says "typically 20 minutes"; we observed
   up to ~30 min). Not directly configurable.
2. **A custom `INCIDENT_TRIAGE` skill** [UG] — if you upload one, it
   overrides the default correlator's decision.

**What the UG does not make obvious:**

- **The platform's title-based dedup runs first and can absorb a task
  before your custom skill meaningfully changes the outcome.** [verified]
  Two tasks with the **same title** within the look-back window get
  LINKed by the platform. If your recurring trigger always uses the
  same title (e.g. `"HyperPod periodic audit: k8-1"`), the platform
  LINKs them regardless of what your custom triage skill would decide.
  - **Fix:** give each fire a **unique title** (we append
    `@ <timestamp>`). This defeats the platform's exact-title dedup so
    the custom skill actually gets to make the decision. Note this
    reverses earlier advice in the solution's own README that
    recommended *stable* titles — that advice predated discovering the
    re-invoke-on-LINK loop.

- **A custom triage skill's decision leaves NO journal record.** [verified]
  It produces only the task's `statusReason` string. You cannot inspect
  the triage skill's reasoning or tool calls via
  `list-journal-records` — that API only shows the RCA (investigation)
  execution. This makes triage-skill debugging hard: you infer behavior
  from the `statusReason` text and the resulting LINK/SKIP/PROCEED
  outcome, not from a trace.

---

## 3. The webhook payload is flattened — only `description` survives intact [verified]

The generic webhook accepts a rich JSON payload (we send `eventType`,
`priority`, `title`, `description`, `data.metadata.*`,
`data.originalEvent.*`, etc.). But when the task reaches the skill, the
backlog task exposes only a small set of fields:

- `title` — preserved verbatim.
- `description` — preserved verbatim (unbounded length, as far as we
  tested — 700+ chars round-tripped fine).
- `reference.{system,title,referenceId,associationId}` — preserved.
- **Nested `data.metadata.*` sub-objects are dropped.** [verified] We
  sent `data.metadata.k8sChecks = {…}` and the skill never saw it — the
  stored task had only the top-level `description`.

**Design implication:** any structured configuration you need the skill
to read at investigation time MUST be **inlined into the `description`
string** (or the title). We inline the `k8sChecks` block as a JSON
snippet at the end of the description with a labeled header line, and
the RCA skill parses it out. Do not rely on nested payload fields
reaching the skill.

> This is why the periodic-audit Lambda builds the description as
> prose + `\n\nk8sChecks configuration (parse as JSON, …):\n{…}`.

---

## 4. Scheduled/`create-trigger` tasks can't run investigations [verified]

`aws devops-agent create-trigger --type TIME_BASED` fires on schedule,
but its `--action` only accepts
`{"actionType":"create:task","task":{"agent":"custom:<assetId>"}}`.
Tested outcomes:

- The trigger fires on its `rate(...)` schedule (confirmed in
  `list-backlog-tasks`).
- It produces a task of `taskType=CUSTOM`, **not** `INVESTIGATION`.
- A `CUSTOM` task runs in a different runtime than an investigation:
  **no AWS API executor** (so `sagemaker:list-clusters` etc. is
  unreachable) and **user skills are not mounted** on its filesystem
  (only `/skills/system/{create-artifact,feedback,recommendations}/`).
- `actionType: "INVESTIGATION"` is rejected verbatim:
  *"action is not supported today; supported actionType values:
  create:task; supported agent values: custom:<assetId>"*.

**Design implication:** to run a real (API-capable, skill-mounted)
investigation on a schedule, you cannot use the native trigger. Instead
use `AWS::Scheduler::Schedule` → Lambda → HMAC-signed POST to the
generic webhook (the same path a real event takes). That produces a
proper `INVESTIGATION` task. This is what the `periodic_audit/` stack
does.

The API error wording ("supported actionType values: create:task")
implies the list is expected to grow; if AWS adds
`create:investigation`, the EB-Scheduler workaround can be replaced by a
single `create-trigger` call.

---

## 5. The permission guardrail is a hard ceiling — IAM grants don't override it [verified/UG]

[UG, p. 365–367] DevOps Agent applies a **permission guardrail**
(a session policy) at AssumeRole time. Effective permissions =
(your IAM role) ∩ (guardrail). The guardrail contains
`AIDevOpsAgentAccessPolicy` (read-only baseline) plus a **closed
opt-in allowlist**. Anything outside that intersection is stripped,
no matter what you attach to the role.

The opt-in allowlist (from the UG) is small:

| Service | Actions | Use |
|---|---|---|
| Athena | `athena:GetQuery*`, `StartQueryExecution`, `StopQueryExecution` | Query data catalog |
| S3 | `s3:GetObject`, `s3:ListBucket` | Read data / logs / configs |
| Direct Connect | `directconnect:Describe*` | Network investigation |
| Glue | `glue:GetPartitions` | Athena partition metadata |
| KMS | `kms:Decrypt` | Decrypt encrypted resources |

**Verified consequences for HyperPod:**

- **`ssm:StartSession` / `ssm:SendCommand` are NOT in the allowlist.** [verified]
  We attached a scoped inline policy granting `ssm:StartSession` on the
  cluster ARN; the agent still couldn't use it — the call surfaced as
  *"blocked because it requires operator approval — classified as a
  mutative operation."* The guardrail stripped it. This means **no
  on-node access** (no `dmesg`/Xid, DCGM, EFA counters, kubelet
  journal, `slurmctld.log`) from DevOps Agent, regardless of IAM. The
  proxy path (HMA CloudWatch streams, K8s node labels,
  `list-cluster-events`) is the only way to see those signals.

- **`aps:*` query actions are NOT in the allowlist.** [verified from UG text]
  The guardrail includes `aps:Describe*` + `aps:List*` only. Amazon
  Managed Prometheus **data-read** actions (`aps:QueryMetrics`,
  `GetLabels`, `GetSeries`, `GetMetricMetadata`) are absent — the agent
  can enumerate AMP workspaces but cannot query time-series. Same shape
  as the SSM limitation.

- **`s3:GetObject` IS in the allowlist** and DOES take effect once
  granted on the role. [verified reasoning] We added an
  `AllowLcsBucketRead` inline policy on `DevOpsAgentRole-AgentSpace`
  scoped to `arn:aws:s3:::sagemaker-*-bucket` so RCA runs can read
  `on_create.sh` instead of hallucinating lifecycle-script content.

- **`kubectl` against the EKS cluster works** via the EKS access entry
  (read-only `AmazonAIOpsAssistantPolicy`), independent of the IAM
  guardrail. Both the RCA skill (`use_kubectl`) and subagents can call
  it. This is the on-cluster (not on-node) path.

**Rule of thumb:** if a capability isn't in `AIDevOpsAgentAccessPolicy`
or the opt-in allowlist above, assume the agent cannot use it and
design a side-channel (write the data to CloudWatch Logs / S3, which
the guardrail can read).

---

## 6. Investigations are alert-driven, never polling [UG]

Out of the box DevOps Agent only investigates when something triggers
it: a webhook POST, a ticket integration, a 3P SaaS hook, or a manual
click. It has no "watch this resource" concept. Any periodic behavior
(our 15-min audit) must be driven from outside via a scheduled webhook
POST. This is why the solution has both a live-event bridge AND a
periodic-audit stack — the platform will not re-check on its own.

---

## 7. The RCA agent will happily skip evidence gathering if not forced [verified]

Observed 2026-07-09: an audit-mode RCA run reached an
`Escalate — recurring lifecycle-script failure pattern` verdict from a
**7-day-old, already-recovered** event history, without ever running
`kubectl get pods` — so it missed a live CrashLoopBackOff pod that was
the actually-actionable signal.

Root cause was skill-instruction shape, not a platform bug: the kubectl
step was written as *conditional* and *late* in the procedure, so the
agent rationalized skipping it ("the event window already gives an
interesting verdict"). Fixes that worked:

- Make the evidence-gather step **mandatory and explicitly
  non-skippable** ("You MUST run this before Phase 2, even if …").
- Add a **sanity gate** that re-checks the required steps ran before
  proceeding to reasoning.
- **Order matters:** put live-state checks *before* historical-pattern
  checks so live signals aren't overshadowed.

General lesson for authoring DevOps Agent skills: the agent optimizes
for reaching a plausible verdict quickly. If a gather step is optional
or buried, it may be skipped. Force-order the evidence collection and
gate the transition to reasoning.

---

## 8. Journal record ordering and types [verified]

`list-journal-records` returns records in **reverse chronological
order** (newest first at index 0). Record types we've seen:

- `message` — the agent's turn-by-turn transcript (role
  `assistant`/`user`, with `text` / `thinking` / `tool_name` parts).
  Tool calls appear as parts with `tool_name` + `input`.
- `symptom` — structured symptom records; the FIRST one is expected to
  be the verdict (title beginning `Triage verdict:`).
- `finding` — root-cause findings.
- `investigation_gap` / `gap` — things the agent couldn't verify.
- `investigation_summary` / `investigation_summary_md` — the final
  report.
- `utilization`, `observation`, `message` — bookkeeping/telemetry.

**Debugging tips:**

- To confirm a skill actually inspected something, grep the joined
  `content` of all `message` records for keywords (e.g. `kubectl`,
  `CrashLoopBackOff`, a pod name).
- A LINKED/SKIPPED task has **no** journal records — its RCA never ran.
- Large tool results are spilled to `/aidevops/large_tool_results/…`
  and read back via `fs_read`; you'll see those file paths in the
  transcript rather than inline data.
- Skills are mounted at `/aidevops/skills/user/<name>/SKILL.md` and
  `/aidevops/skills/user/<name>/references/…`. Agent memory lives under
  `/aidevops/memory/…`.

---

## 9. Skill versioning and upload behavior [verified]

- Uploading a skill with the same `name:` creates a new version
  (`ListAssets` shows an incrementing `version`); the newest ACTIVE
  version is used.
- **There can be propagation lag.** We saw a task get triaged by the
  *previous* skill version shortly after an upload — re-uploads are not
  guaranteed instant for already-queued tasks. When testing a skill
  change, fire a *fresh* trigger after the upload rather than trusting
  an already-in-flight task to use the new version.
- Two skill "types" appear in `list-skills`: **USER** (what we author)
  and **LEARNED** (what the agent generates about the environment, e.g.
  `understanding-agent-space`). Don't edit LEARNED skills.

---

## 10. Investigation console URL shape [verified]

The working per-investigation console URL is:

```
https://<region>.console.aws.amazon.com/aidevops/home?region=<region>#/agentspaces/<agent_space_id>/investigations/<task_id>
```

An earlier guessed shape (`…#/investigations/<investigation_id>`
without the agent-space segment) 404s. The email notifier's
`CONSOLE_URL_TEMPLATE` uses the working form with `%agent_space_id%`
and `%task_id%` tokens.

---

## 11. Quotas and regional notes [UG]

- Agent Space is available only in a fixed set of regions — confirm
  `aidevops.<region>.amazonaws.com` resolves before deploying.
- Quotas: 100 agent spaces / region; **3 concurrent investigations /
  space** (adjustable); 10 concurrent on-demand invocations / space.
  The 3-concurrent limit is why back-to-back audit fires queue at
  `PENDING_START` when several investigations are already running.
- One Agent Space with an `Aws` monitor association discovers resources
  across **all regions** of the account — cross-region monitoring is
  implicit, but the Agent Space resource itself is single-region.

---

## Things still unclear / under investigation

- **Whether a custom `INCIDENT_TRIAGE` skill can call `use_aws` /
  `use_kubectl` at all, or runs in a restricted tool sandbox.** We
  designed triage v0.6 assuming it can compute a cluster signature via
  kubectl + `list-cluster-events`, but because triage leaves no journal
  we could not confirm the tools actually executed. The PROCEED
  outcomes we saw are also explainable by the platform default
  correlator (unique titles → no dedup → PROCEED). **Open question:
  does our triage skill's gather logic actually run?** Needs a
  controlled test — e.g. a trigger the platform default would LINK but
  our signature logic would PROCEED, or vice-versa, with the outcome
  distinguishing which decided.
- **Exact platform look-back window.** UG says "typically 20 minutes";
  we've observed LINK behavior consistent with ~20–30 min, but it's not
  a documented, configurable knob.
- **Whether nested payload fields are ever preserved** (e.g. under a
  different top-level key than `data.metadata`). We only confirmed
  `description`/`title`/`reference` survive; we did not exhaustively
  probe which envelope fields the platform keeps.
- **Duplicate `Investigation Completed` emission frequency.** We know
  the platform re-emits it (the email notifier dedups via an S3 marker
  keyed by `execution_id`), but not the exact trigger or cadence.
