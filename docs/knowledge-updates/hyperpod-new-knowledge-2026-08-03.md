# HyperPod Mental Model — New Findings (2026-08-03)

Findings from validating [`hyperpod-mental-model.md`](hyperpod-mental-model.md)
against two live HyperPod clusters while building the **HyperPod Cockpit** tool
(a read-only, per-user monitoring app over the SageMaker service APIs). This file
is a staging area for the mental-model doc's maintainer: **confirmations** (claims
that held under live test) and **proposed edits** (gaps worth folding into the
main doc).

## Test environment

| Cluster | Orchestrator | ARN suffix | `NodeProvisioningMode` |
|---|---|---|---|
| `slurm-2` | Slurm | `cluster/uy8s15oijdlw` | `Continuous` |
| `k8-1` | EKS | `cluster/lw12e0dn1hhd` | `Continuous` |

Account `842413447717`, region `us-west-2`. All calls **read-only**
(`describe*` / `list*`). API shapes cross-checked against the botocore SageMaker
service model (`2017-07-24`) for the full possible field set.

## Confirmations (mental model held under live test)

1. **`describe-cluster-event` returns a double-nested shape** —
   `EventDetails.EventDetails.EventMetadata.<subtree>`. The example at
   mental-model.md lines ~690–709 shows this; confirmed verbatim against a live
   event. Notably confirmed on **Slurm** (`slurm-2`), not just EKS.

2. **`ListClusterEvents` `MaxResults` hard cap is 100.** `--max-results 200`
   returns `ValidationException: Member must have value less than or equal to
   100`. Consistent with the doc's "up to 5 pages of 100" (line ~439).

3. **`describe-cluster-event` requires `NodeProvisioningMode: Continuous`.** Both
   clusters are Continuous, and the call succeeds on both. (See proposed edit #1 —
   this precondition is orchestrator-independent, not EKS-specific.)

4. **The service-layer read APIs are orchestrator-agnostic.** `DescribeCluster`,
   `ListClusterNodes`, and `DescribeClusterNode` return the **same shape** on both
   orchestrators, differing only in an `Orchestrator` discriminator (`{"Slurm":{}}`
   vs `{"Eks":{"ClusterArn":...}}`) and small sub-blocks (`SlurmConfig` with
   `NodeType`/`PartitionNames`; EKS cluster-level `AutoScaling`/Karpenter; EKS node
   `KubernetesConfig` labels/taints). Reinforces the doc's framing that node
   lifecycle is a *service* concern, uniform across orchestrators.

5. **`describe-cluster-node` carries no health/resiliency payload.** Confirms
   mental-model.md lines ~935–945: the only node health signal in that API is
   `InstanceStatus.Status`. Full enum (from the service model):
   `Running | Failure | Pending | ShuttingDown | SystemUpdating |
   DeepHealthCheckInProgress | NotFound`. No DCGM/EFA fields, no replacement
   events, no topology labels.

6. **`list-cluster-events` is the customer-visible resiliency feed on Slurm too.**
   `slurm-2` (Continuous) returned real instance deletion/ENI-cleanup events with
   `EventLevel`, `ResourceType`, `EventTime`, `Description`. Matches the doc's note
   that the API works on "Slurm with Continuous Provisioning," not EKS-only.

## Proposed edits to the mental model

### 1. Clarify that `describe-cluster-event`'s Continuous-mode gate is orchestrator-independent

**Where:** "Event surfaces" → "`FailureMessage` is only in `describe-cluster-event`
today" (line ~669), tagged *(Both — verified on EKS …)*, and the precondition note
at line ~716.

**Gap:** The section reads as EKS-centric, but the real precondition is
`NodeProvisioningMode: Continuous`, not the orchestrator. Verified live: the API
succeeds on the **Slurm** cluster `slurm-2` because it is Continuous. The doc's own
line ~439 already hedges with "Slurm with Continuous Provisioning" — the two spots
should agree.

**Proposed wording:** "`describe-cluster-event` / `list-cluster-events` are gated on
`NodeProvisioningMode: Continuous`, independent of orchestrator. Both Slurm and EKS
clusters expose them when Continuous; non-Continuous clusters of either type return
`ValidationException`."

### 2. Call out the double-nested `EventDetails.EventDetails` shape as a parsing hazard

**Where:** "Event surfaces" → near "SageMaker `EventId` vs EventBridge `id`"
(line ~784), which already warns about a nested-field footgun.

**Gap:** The `describe-cluster-event` response nests `EventDetails` **twice**: the
top-level `EventDetails` holds `EventId`, `Description`, `EventLevel`, `EventTime`
directly, while `EventMetadata` sits one level deeper under a *second*
`EventDetails`. The example shows it, but there's no explicit "watch the double
nesting" note. It's an easy off-by-one-level bug for client authors.

**Proposed wording (new bullet):** "The `describe-cluster-event` response nests
`EventDetails` twice —
`response['EventDetails']['EventDetails']['EventMetadata'][<subtree>]` — while
`EventId` / `Description` / `EventLevel` sit at the first `EventDetails` level.
Confirmed on both orchestrators. Don't assume a single `EventDetails`."

### 3. Resolve (or downgrade) an item in "Things still unclear"

**Where:** "Things still unclear / under investigation," line ~1611: *"(Slurm) Does
`UpdateClusterSoftware` rewrite `slurm.conf` from scratch (clobbering operator
edits)?"*

**Gap:** The "Lifecycle scripts" section (line ~584) and the "`UpdateClusterSoftware`
AMI repaint" callout (line ~503) already establish that `UpdateClusterSoftware`
wipes root EBS and re-runs `on_create.sh` on a fresh AMI — which implies
`slurm.conf` is regenerated by the cluster agent, not preserved. This open question
looks answerable from content already in the doc; consider resolving it or
narrowing it to the still-genuinely-open part (exactly which fields the agent
regenerates vs. preserves, per the caveat at line ~340).

### 4. Add: the `AWS-StartNonInteractiveCommand` document is argv-split, not a shell

**Where:** "Reaching nodes via SSM" (line ~1304) and the `ssm:SendCommand` note
(line ~1282), which already establish `start-session` as the only remote-exec path
and mention the `unbuffer`/EOF mitigation.

**Gap:** Neither spot notes that the `AWS-StartNonInteractiveCommand`
document **splits its `command` on spaces and exec's it as argv — there is no
shell**. Pipes, redirects, `$(...)`, and `bash -c "..."` passed as one element all
fail silently or error (`Unknown options: |, head`). A bare command like `sinfo -V`
works; anything needing a shell must invoke `bash` explicitly as separate argv
elements (`["bash","-lc","<script>"]`) — and even that was flaky in testing. This
bit me repeatedly while running the spikes; worth one sentence so client authors
don't rediscover it.

**Verified live (2026-08-03):** on `slurm-2`, bare `aws sts get-caller-identity
--output text` returned cleanly; `... | head -3` errored with `Unknown options`.

**Follow-up — the argv-split limitation is avoidable; document the workaround too.**
The robust pattern (implemented in `hyperpod_run_on_multi_nodes/`, in this repo) is
to skip `AWS-StartNonInteractiveCommand` entirely and drive an **interactive**
`aws ssm start-session` PTY with `pexpect`: ship the script as one base64 line
(`echo <b64> | base64 -d | bash -s --`) so the real script rides inside the blob
(no shell needed on the wire), and mark end-of-output with a runtime-assembled
sentinel (`S="…"; T="…"; <cmd>; echo "$S$T"`) so `expect` can't false-fire on the
echoed input. Practical limits worth a line in the doc: **~3500 B on the wire per
`sendline`** (kernel `MAX_CANON=4096` PTY line-buffer cliff — silent truncation +
hang past it), **~3 s** per-node session startup, and **3 TPS/account**. Consider
pointing the SSM section at this pattern rather than leaving readers with the
argv-split document as the only documented option.

### 5. Confirms: `slurmrestd` is off by default (both the doc's hedge and mine agree)

The doc's line ~439 hedges "Slurm with Continuous Provisioning"; separately, this
session confirmed `slurmrestd` itself is `inactive` + `disabled` on `slurm-2`'s
controller. If the doc doesn't already state the default-off status of the REST
daemon explicitly, it's worth a line — tooling authors tend to assume it's on.

### 6. Confirms: node ExecRole cannot call cluster read APIs

The node's `sagemaker-slurm-2-…ExecRole` gets `AccessDeniedException` on
`DescribeCluster` / `ListClusterNodes` / `ListClusterEvents`. Reinforces the doc's
ownership-boundary framing and the "operator access is via SSM, then Slurm" note
(line ~73): the ambient node identity is deliberately not a cluster-management
identity.

## Not yet verified (kept honest)

These mental-model claims were **not** exercised in this session — the clusters
were in steady state and I ran only read-only APIs. Flagging so no one reads the
confirmations above as broader than they are:

- Detection→recovery flow (HMA marking `Action:Reboot`/`Action:Replace`, the
  20–30 min replacement window, `Failed`→retry behavior). No faults were injected.
- On-node/SSM claims (agent netns ports, systemd unit presence, configless slurmd,
  config-file paths). No SSM sessions were opened.
- EventBridge envelope behavior (null `EventMetadata` subtrees, paired events,
  EventBridge `id` vs SageMaker `EventId`). Only the direct SageMaker APIs were
  called, not the EventBridge delivery path.
- The `describe-cluster-node.DesiredImageId` "data-plane shared AMI" bug — no
  `UpdateClusterSoftware` was in flight.

## Relevance to HyperPod Cockpit

Captured in the Cockpit repo at `docs/service-api-findings.md`. Net effect on the
tool's design: the resiliency panel reads `list-cluster-events` (poll) +
`describe-cluster-event` (on-demand detail), the overview/utilization panels detect
scaling via `CurrentCount` vs `TargetCount` (never `ClusterStatus` alone under
Continuous mode), and deep-health numeric results come from CloudWatch Logs
(`DeepHealthCheckResults/<id>`), not any SageMaker read API.
