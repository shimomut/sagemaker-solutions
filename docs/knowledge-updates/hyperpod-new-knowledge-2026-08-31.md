# HyperPod Mental Model — New Findings (2026-08-31)

Findings from a survey of the **AMI-versioning fields** on
`ClusterInstanceGroupDetails` (`CurrentImageId`, `CurrentImageReleaseVersion`,
`DesiredImageId`, `DesiredImageReleaseVersion`, `ImageVersionStatus`) across
every cluster reachable from one account, prompted by a test campaign that
needed to answer *"which AMI is this node actually running?"* from the API alone
and could not. Validating / extending
[`../hyperpod-mental-model.md`](../hyperpod-mental-model.md), specifically the
`UpdateClusterSoftware` semantics section (lines ~535–566).

## Test environment

| Cluster | Orchestrator | `NodeProvisioningMode` | Created | Notes |
|---|---|---|---|---|
| `slurm-1` | Slurm | absent (OnStart) | 2026-01-14 | never patched |
| `slurm-2` | Slurm | `Continuous` | 2026-07-10 | |
| `slurm-ctrl-resil-test2` | Slurm | absent (OnStart) | 2026-08-31 | Console-created |
| `k8-1` | EKS | `Continuous` | 2026-06-15 | patched 2026-07-02 |
| `preefs2664` | Slurm | absent (OnStart) | — | **alpha** endpoint; created with a cluster-level custom AMI pin |

Account `842413447717`, region `us-west-2`; the last row via the alpha endpoint,
the rest prod. All calls **read-only** (`describe-cluster`, `list-cluster-nodes`,
`describe-cluster-node`). Cross-checked against the botocore SageMaker model
(`2017-07-24`) in use, which **does** define all five fields — so every absence
below is the service omitting the field, not a stale client model. (Worth
checking explicitly: if `~/.aws/models/` contains a hand-added `sagemaker`
override, `aws sagemaker` is not using the CLI's bundled model at all, and
"the API doesn't return X" can be a tooling artifact.)

## Proposed edits to the main doc

### 1. `CurrentImageId` is a *custom-AMI* field; `default` is the managed-AMI sentinel

**Where:** `UpdateClusterSoftware` operational semantics (after the
`describe-cluster-node` `DesiredImageId` bug callout, ~line 552)

**Gap:** The main doc uses `CurrentImageId` as if it always names an AMI ("check
`CurrentImageId` after the update settles — that returns to the customer's owned
AMI"), which is true in the custom-AMI campaigns it was written from. It never
says what the field returns when the node is on a **HyperPod-managed** AMI. The
public API reference doesn't say either — its prose is just "The ID of the AMI
currently in use by the instance group"; the only hint is the value pattern
`ami-[0-9a-fA-F]{8,17}|default`.

**Proposed wording:**

> **`CurrentImageId` / `DesiredImageId` exist to report a *custom* AMI.** When
> the node is on a HyperPod-managed AMI, they return the literal string
> `default`, not an `ami-…` id — so these fields answer "is this instance group
> pinned to a customer AMI, and which one?", **not** "which AMI image is this
> node running?". There is no API that answers the second question for a
> managed-AMI node; the release-version fields are the intended substitute, and
> they are not always populated (below). Measured: `default` on every
> managed-AMI instance group across one Slurm and one EKS cluster, at both the
> instance-group and node level.

### 2. Population of the image fields tracks `NodeProvisioningMode`, not orchestrator

**Where:** same section; also worth a row in "Common AI-confusing details"

**Gap:** Not covered at all. The API reference documents no orchestrator or
mode restriction on these fields, so a reader reasonably assumes they are
always present.

**Proposed wording:**

> **The image fields are only populated on Continuous Provisioning clusters,
> and `CurrentImageReleaseVersion` is scarcer still.** Measured across five
> clusters:
>
> | Cluster | Orchestrator | Mode | `Current/DesiredImageId` | `Current/DesiredImageReleaseVersion` | `ImageVersionStatus` |
> |---|---|---|---|---|---|
> | `slurm-1` | Slurm | OnStart | absent | absent | present |
> | `slurm-ctrl-resil-test2` | Slurm | OnStart | absent | absent | present |
> | `preefs2664` | Slurm | OnStart | absent | absent | present |
> | `slurm-2` | Slurm | **Continuous** | `default` | absent | present |
> | `k8-1` | EKS | **Continuous** | `default` | `1.3.0` on **2 of 5** IGs | present |
>
> Two things follow. First, **orchestrator is not the discriminator** —
> a Slurm cluster in Continuous mode returns the image-id fields just like EKS
> does; the clusters that omit them are the ones not in Continuous mode.
> Second, **`ImageVersionStatus` is the one field present everywhere**, on all
> five clusters and every instance group — so it is the only member of this
> group a runbook can rely on, and it reports *whether* an update exists
> (`UpToDate` / `UpdateAvailable` / `SecurityUpdateRequired`), never *what
> version you are on*.

### 3. A cluster-level custom-AMI pin is invisible on every API surface

**Where:** same section

**Gap:** Not covered. Someone who reads edit #1 will reasonably conclude "so a
custom AMI *will* show up in `CurrentImageId`" — which was not true in the one
case measured here.

**Proposed wording:**

> **A cluster-level custom AMI pin does not surface anywhere.** A Slurm cluster
> created with a cluster-level `--cluster-ami ami-0ec2f365f2693316a` returned
> **no** cluster-level `ImageId` on `describe-cluster`, no `CurrentImageId` on
> its instance groups, and no image fields on `describe-cluster-node`. So
> "`CurrentImageId` is the custom-AMI field" describes its *purpose*, not a
> guarantee that a custom AMI is discoverable — on a non-Continuous cluster
> neither the pin nor the managed-AMI sentinel appears. (Measured on the alpha
> endpoint; not re-measured in prod, and the two behaviors could differ.)

### 4. On Slurm there is no API answer to "which AMI vintage is this node?"

**Where:** "Where to find data" (~line 1346) and/or "Common AI-confusing details"

**Gap:** The doc explains at length how `UpdateClusterSoftware` repaints the
root volume, but not how to find out *whether* a given node has been repainted
and onto what.

**Proposed wording:**

> **There is no API that reports a Slurm node's running AMI.** Not
> `describe-cluster` (`ImageId` absent even when pinned cluster-level), not
> `list-cluster-nodes`, not `describe-cluster-node`, and `ec2 describe-instances`
> cannot see the instances at all — they live in a service-owned account. On
> Continuous-mode clusters `CurrentImageId` narrows it to
> "managed (`default`) vs a named custom AMI"; the release-version fields, which
> would answer it properly, are populated on EKS only (and not on every instance
> group). **IMDS on the node over SSM (`curl
> http://169.254.169.254/latest/meta-data/ami-id`, token-authenticated) is the
> only way to learn a Slurm node's actual AMI id.**
>
> `LastSoftwareUpdateTime` is a weak substitute: on 4 of the 5 clusters measured
> it exactly equalled the node's `LaunchTime`, so "never patched since launch"
> and "patched at launch" are indistinguishable. It does move when a real patch
> lands (`k8-1`: launched 06-15, `LastSoftwareUpdateTime` 07-02), so treat a
> value *later* than `LaunchTime` as evidence of a patch and a value *equal* to
> it as no evidence either way.

## Not yet verified (kept honest)

- **Why `CurrentImageReleaseVersion` appeared on only 2 of `k8-1`'s 5 instance
  groups.** Both populated groups are `ml.g5.*` and the three empty ones are
  `ml.m5` / `ml.g6.*`, but instance family is almost certainly a coincidence —
  IG creation or last-patch time is the more likely driver, and neither is
  exposed per-IG. Not enough data to state a rule.
- **Whether the Continuous-mode correlation is causal.** It is a clean 3-absent
  / 2-present split across five clusters, and no other attribute (orchestrator,
  age, patch history, console-vs-CLI creation) splits them the same way — but
  five clusters in one account is not a mode gate proven from the service side.
  It could equally be a cluster-vintage effect that happens to align with when
  Continuous mode became the default.
- **Whether `CurrentImageId` returns a real `ami-…` on a Continuous-mode
  cluster with a custom AMI.** Not measured — no such cluster was available.
  This is the case that would confirm edit #1's second half directly rather
  than by inference from the API-reference pattern.

## Open questions

- **Is "HyperPod Slurm does not support AMI Versioning yet" the intended state,
  and is there a published mapping from release version → what shipped in it?**
  A version number like `1.3.0` only answers an operator's real question ("does
  my fleet have feature X / patch Y?") if someone publishes which release first
  contained it. Without that mapping the field is an opaque ordinal.
- **Is `ImageVersionStatus` stable once a cluster is `InService`?** Observed
  flipping to `UpdateAvailable` on 2 of 20 identical back-to-back calls against
  a freshly-patched `InService` cluster, so a runbook that gates on a single
  read of it can act on a stale answer. Worth a retry/settle note if confirmed.
