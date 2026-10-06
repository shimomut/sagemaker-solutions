# HyperPod Mental Model — New Findings (2026-10-05)

Findings from reviewing the SageMaker AI console's HyperPod cluster detail page
while explaining Ray-on-HyperPod setup. The console has gained a **Ray panel**
that the extracted developer-guide chapter
(`hyperpod_ray/docs/ray-on-hyperpod.md`) does not describe. Follow-up to
[`hyperpod-new-knowledge-2026-09-09.md`](hyperpod-new-knowledge-2026-09-09.md).

## Test environment

Console observation: HyperPod cluster `k8-1`, us-west-2, account 842413447717,
`Admin/shimomut-Isengard`. Cross-checked read-only against the EKS add-on
catalog (`aws eks describe-addon-versions`, us-west-2) and the public SageMaker
API model (botocore 1.42.34). Call scope: read-only.

## New topics (not yet covered)

- **The console has a "Ray" add-on panel that reports KubeRay status but does not
  install it.** The panel sits in the cluster's add-on list with a `New` badge, a
  `Status` line (`Not installed` on a cluster without KubeRay), a `Ray features`
  readiness table, and an `Install` dropdown. **Pressing `Install` opens the
  developer-guide page "Installing KubeRay on HyperPod Amazon EKS"** — it does not
  install anything. Verified 2026-10-05 on `k8-ray-3`; the live HTML page is
  substantively identical to the PDF chapter and documents only
  `helm repo add kuberay … && helm install`, with no console path.

  So the panel's contribution is **discovery and status**, not automation. There is
  no GUI installation path for KubeRay. Candidate supplemental doc:
  `mental-model/hyperpod-ray.md`.

- **The panel's status reads real cluster state, not console history.** Verified
  2026-10-05: after installing KubeRay entirely by hand (Helm, chart 1.7.1, into a
  dedicated `kuberay-operator` namespace, no console involvement), the panel flipped
  to `Status: Installed` and its button changed from `Install ⌄` to `Actions ⌄`.
  This is the important half of the panel being worth anything: the status stays
  accurate on clusters built by IaC, so the console reports while CloudFormation or
  Helm acts. It also matches the `Ray features` rows, which track add-on presence
  correctly across two clusters. Installing KubeRay changed none of those rows,
  which is correct — they concern other add-ons.

- **Reconciling this with the PM statement.** The service PM said on 2026-10-05
  that the console Ray install "is a wrapper around `helm install`". Observed
  behavior is a link to a page describing `helm install`. Readings that fit both,
  in rough order of likelihood: the PM meant *there is no managed install
  mechanism, it is just Helm* (true either way); the actual installer is not yet
  shipped to this account or Region; or another item in the `Install` dropdown
  does install and only the one pressed was a doc link. **Unresolved**: the
  dropdown's full contents were not recorded — press it and read the items before
  concluding.

  The practically important part holds regardless: **KubeRay on HyperPod is an
  ordinary Helm release**, subject to `helm list` / `helm upgrade` /
  `helm uninstall`, and there is no EKS managed add-on for it.

- **Two KubeRay installs collide on cluster-scoped objects, not on the release.**
  Worth recording because the intuition is wrong in both directions. The
  documented command (`helm install kuberay-operator kuberay/kuberay-operator`)
  names no namespace and so lands in the current context's — `default` in
  practice. `hyperpod_ray/cfn/kuberay-operator.yaml` defaults to a
  `kuberay-operator` namespace. Helm releases are namespace-scoped, so those are
  two *distinct* releases and neither overwrites the other. But the chart installs
  cluster-scoped CRDs and RBAC, and those have one owner. Verified on 2026-10-05
  with `--dry-run=server` against a cluster already carrying the manual install:

  ```
  Error: INSTALLATION FAILED: unable to continue with install: ClusterRole
  "raycronjob-editor-role" in namespace "" exists and cannot be imported into the
  current release: invalid ownership metadata; annotation validation error: key
  "meta.helm.sh/release-namespace" must equal "kuberay-operator": current value is
  "default"
  ```

  The second install **refuses** rather than corrupting anything, which is the
  good failure mode. Consequence: a CloudFormation install fails on any cluster
  where someone already ran the documented command, until that release is
  uninstalled.

  **The same-namespace case is the dangerous one.** If the hand install is moved
  to `kuberay-operator` — the namespace the stack defaults to — there is no
  conflict at all, because the stack runs `helm upgrade --install`, which *adopts*
  an existing release. Deploying the stack then succeeds, silently sets the chart
  to whatever `ChartVersion` says (default 1.7.0, a downgrade from 1.7.1), and
  leaves CloudFormation owning a release it did not create — including on stack
  delete, where it runs `helm uninstall`. Inferred from the template code plus
  Helm semantics, not executed. The lesson is to pick one path per cluster.

- **`helm uninstall` leaves the CRDs and removes the cluster-scoped RBAC.**
  Verified 2026-10-05. Helm never deletes `crds/` contents, so the four `ray.io`
  CRDs survive an uninstall with no Helm ownership annotations, while templated
  `ClusterRole`s and `ClusterRoleBinding`s go. That asymmetry is why a reinstall
  into a *different* namespace succeeds after an uninstall but fails before one:
  the CRDs are adopted silently, and the RBAC that would have conflicted no longer
  exists. It is also the mechanism behind the documented warning that uninstalling
  the operator does not remove your Ray resources.

- **The documented install command puts a cluster-wide operator in `default`.**
  `helm install kuberay-operator kuberay/kuberay-operator` names no namespace, so
  it takes the current context's. Worth flagging as a documentation-quality issue:
  the page gives no `-n`/`--create-namespace` and no `--version`, so a reader
  following it exactly gets an unpinned operator in `default`. The upstream KubeRay
  docs the page links to do use a dedicated namespace.

- **The documented command resolves to whatever is latest, and the doc page never
  mentions a floor.** On 2026-10-05 that was chart **1.7.1** (operator image
  `quay.io/kuberay/operator:v1.7.1`), comfortably above the effective ≥ 1.6.0
  floor — but by luck, not by instruction. The chart also sets no `appVersion`, so
  `helm list` shows an empty `APP VERSION` column and the image tag is the only
  place the operator version is visible.

- **The console Ray install is still not an EKS managed add-on.** Verified
  2026-10-05: the us-west-2 EKS add-on catalog has
  `amazon-sagemaker-hyperpod-inference`, `amazon-sagemaker-spaces`,
  `amazon-sagemaker-hyperpod-observability`,
  `amazon-sagemaker-hyperpod-training-operator`, and
  `amazon-sagemaker-hyperpod-taskgovernance` — and nothing matching `kuberay` or
  `ray`. So the 2026-09-09 finding "KubeRay has no EKS add-on — it is Helm-only"
  still holds at the mechanism level; what changed is that the console drives
  the Helm install. The public SageMaker API model also exposes no add-on
  operations or shapes at all (no `*AddOn*` operation or shape in
  botocore 1.42.34), so add-on installation is not scriptable through
  `aws sagemaker` either way.

- **A per-feature readiness table ("Ray features") is the authoritative setup
  checklist.** Each Ray capability gets a row with a `Status` and a deep-link
  `Action`, which turns the "optional add-ons" prose of the chapter into
  something inspectable per cluster. Observed rows and statuses:

  | Ray feature | Status | Action |
  |---|---|---|
  | Ray development environments | Add-on not installed | Install SageMaker Spaces add-on |
  | Secure Ray dashboard access | Add-on not installed | Install SageMaker Spaces add-on |
  | SageMaker Studio for Ray development | – | Set up SageMaker Studio with HyperPod |
  | Ray observability | Add-on not installed | Install HyperPod Observability add-on |
  | Ray workload prioritization and quotas | **Available** | – |
  | Hung job detection | **AMI out of date** | Update AMI to Aug 18, 2026 or newer |
  | Tiered checkpointing with Ray Train | Not configured | Configure tiered storage |
  | Managed tiered KV cache with Ray Serve | Not configured | Configure tiered storage |

  Two things worth reading off this: "Secure Ray dashboard access" is attributed
  to the **Spaces add-on**, not to the Ray Endpoint Operator by name (consistent
  with the chapter, where the Endpoint Operator *depends on* Spaces with web
  browser access enabled — the console collapses that chain into one action);
  and task governance queueing reports `Available` with no action, i.e. it is
  satisfied by the taskgovernance add-on already on the cluster.

- **Studio access to a HyperPod cluster is two grants, and conflating them costs
  hours.** Both are documented in "Setting up an Amazon EKS cluster in Studio"
  (`sagemaker-hyperpod-studio-setup-eks.html`), which the Ray chapter points to as
  *"Setting up an Amazon EKS cluster"*:

  1. **An IAM policy on the execution role**, letting it call AWS APIs. The
     statement that matters is `eks:AccessKubernetesApi` — without it the EKS
     authorizer refuses every call *before* RBAC is consulted, so nothing else can
     compensate. **`AmazonSageMakerFullAccess` contains no `eks:` actions at all**
     (verified by searching its 24 KB document), so a role built from that managed
     policy alone cannot reach the cluster. The policy also needs **two different
     cluster ARNs** — `sagemaker:DescribeCluster` on the HyperPod cluster, the
     `eks:` actions on the EKS cluster — and `eks:DescribeAddon` on the
     sub-resource ARN `cluster/<name>/*`, which is how Studio detects the Spaces
     add-on.
  2. **EKS cluster-access policies**, which grant permissions inside the cluster
     and are what `Manage access` attaches.

  **Their scopes are not uniform**, and this is easy to get wrong in automation:
  `AmazonSagemakerHyperpodUserClusterPolicy` must be attached at **cluster** scope
  (it carries the cluster-wide reads the UI needs to render), and
  `AmazonSagemakerHyperpodSpaceTemplatePolicy` must be scoped to
  **`jupyter-k8s-shared`**, where the shared templates live, not to the namespace
  the users work in. The remaining three follow your own namespace choice, and
  scoping them also restricts which tasks those users see.

- **Studio reports a 403 as "The Custom Resource Definition (CRD) of type … is not
  configured on the cluster".** The CRD exists; the caller simply cannot read it.
  **Reportable as a bug**, and the one finding from this investigation that is. The
  wording sent us through three wrong hypotheses in order — missing CRD, stale Helm
  chart, wrong access-policy scope — when the actual cause was the IAM policy, and
  was documented. The mechanism: `AmazonSagemakerHyperpodUserClusterPolicy` carries
  `apiextensions.k8s.io/customresourcedefinitions get` and
  `authorization.k8s.io/selfsubjectaccessreviews create`, which are how the UI
  probes for a CRD and for the user's own access. When the probe is itself refused,
  its failure is rendered as absence. A secondary symptom: changing the task type
  then appears to do nothing and the banner keeps naming the old type, which reads
  like a UI bug but is just every request being refused.

- **`AmazonSagemakerHyperpodTrainingPolicy` grants `ray.io` outright** — "full
  access to RayCluster, RayJob, and RayCronJob" per its documented description.
  Confirmed empirically: a hand-written `ray.io` ClusterRole was deleted and Studio
  kept listing the RayCluster. **No custom RBAC is needed for Ray.** Recording this
  because the opposite was concluded earlier in the session from reading the Helm
  chart and the cluster-setup Lambda, neither of which mentions `ray.io` — the
  mistake was assuming those were the only sources of in-cluster permission, when
  the access policies are a parallel and sufficient mechanism.

- **Skipping the data-scientist parameters at cluster creation is what leaves this
  unconfigured.** `DataScientistSetupCondition` in the official EKS main stack is
  false when `DataScientistRole1` … `DataScientistRole10` are all empty, so the
  entire `DataScientistSetupStack` is skipped and no IAM policy or access entry is
  created. Populate them at creation time if anyone will use Studio.

  Worth knowing what that stack actually does, because it takes the *other*
  documented route: its Lambda
  (`1/resources/data-scientist-setup/lambda_function/lambda_function.py`,
  2026-09-30) attaches IAM policy `HyperPodDataScientistUI-<cluster>`, creates an
  access entry with `kubernetesGroups` and **no access policies**, and applies its
  own ClusterRole plus per-namespace Role. That RBAC covers
  `kubeflow.org/pytorchjobs` and `inference.sagemaker.aws.amazon.com` but **not
  `ray.io`** — so a cluster set up purely that way shows PyTorch tasks and not Ray
  ones. The guide documents this custom-RBAC route as an alternative to the
  cluster-access policies, for granting a narrower set of verbs.

- **EKS access policies cannot be tested with `kubectl auth can-i --as`.** The EKS
  authorizer evaluates them outside of Kubernetes RBAC, so impersonation reports
  `no` for permissions that work. Only group-bound RBAC — the custom-role route —
  is testable that way. Recording this because the distinction produced a wrong
  conclusion mid-session: an impersonation test was read as proof that
  cluster-scoped access policies were ineffective, which it could not show.

- **`aws cloudformation deploy` keeps the previous value of any parameter it is not
  given.** Two distinct ways this bites, both hit in one session: a wrapper that
  passes a parameter only when non-empty creates a setting you can set but never
  clear; and changing a parameter's *default in the template* has no effect on an
  existing stack, so a policy whose `Attach…` default flipped to `true` silently
  stayed off through a redeploy. Pass every parameter every time, or check
  `describe-stacks --query 'Stacks[0].Parameters'` afterwards.

- **Following the Ray chapter verbatim produces a space that cannot talk to its Ray
  cluster.** Both halves come from the documentation, and they disagree:

  | Side | Documented source | Python |
  |---|---|---|
  | `RayCluster` | the chapter's own manifests use `rayproject/ray:2.55.1` (and `2.56.1`) | 3.10.20 |
  | Space | the default space template's `sagemaker-distribution:latest-cpu` | 3.12.14 |

  The **Ray versions match** at 2.55.1, which is what makes this easy to walk into,
  and Ray refuses the connection anyway — its `check_version_info()` compares Python
  too, at `ray.init()`:

  ```
  RuntimeError: Version mismatch: The cluster was started with:
      Ray: 2.55.1
      Python: 3.10.20
  This process ... was started with:
      Ray: 2.55.1
      Python: 3.12.14
  ```

  The chapter does state the requirement ("The Python version must match as well,
  including the patch version") and recommends using the same SageMaker Distribution
  image on both sides. But its own examples do not follow that advice, so the
  happy path through the documentation is the broken one. **Reportable:** either the
  chapter's `RayCluster` examples should use the Distribution image, or the space
  template default should match the examples.

- **Studio reports `Connected` for a combination that cannot work, with no warning.**
  The chapter claims "When the versions differ, Studio shows a warning and offers to
  create a compatible cluster instead." On Spaces add-on **v0.2.0-eksbuild.2** no
  warning appeared; the `Connect Ray cluster` dialog accepted the cluster and the tab
  reported `Connected`. The validation appears to compare `rayVersion` only.
  **Reportable as a bug**, and a close cousin of the 403-as-missing-CRD finding: the
  console's status is accurate about something narrower than what the user reads it
  as. `Connected` is true — the space pod does join the cluster, and the injected
  `ray-sidecar` cannot mismatch because it runs the cluster's own head image — but
  the user's Python process is refused.

- **`Quick Install` does not install the latest add-on version.** It installed
  `amazon-sagemaker-spaces` **v0.2.0-eksbuild.2** while the catalog offered
  `v0.2.1-eksbuild.1`. It clears the ≥ 0.2.0 floor Ray needs, but "Quick Install"
  should not be read as "current". It also pulls in `aws-ebs-csi-driver` and
  cert-manager as prerequisites, and creates three IAM roles (controller, in-cluster
  router for KMS/JWT, SSM managed node).

- **The space templates are not in the namespace the docs name.** The guide says to
  scope `AmazonSagemakerHyperpodSpaceTemplatePolicy` to `jupyter-k8s-shared` "where
  the templates live". On v0.2.0-eksbuild.2 the `WorkspaceTemplate`s, the access
  strategy and the `ray-integration` integration template are all in
  **`jupyter-k8s-system`**, and `jupyter-k8s-shared` does not exist. Scoping an EKS
  access policy to a non-existent namespace is accepted and silently grants nothing,
  so this fails invisibly.

- **The Ray integration is a sidecar that inherits the cluster's head image.** The
  `ray-integration` WorkspaceIntegrationTemplate injects a container into the space
  pod with
  `image: {{ resource "rayCluster" "{.spec.headGroupSpec.template.spec.containers[0].image}" }}`
  and runs `ray start --address=<head-svc>.<workspace-namespace>.svc.cluster.local:<gcs-port>
  --num-cpus=0 --num-gpus=0 --block`, retrying 30 times at 10s intervals. Three
  consequences worth knowing: the space **must** be in the same namespace as the Ray
  cluster, since the address is built from the workspace's namespace; `ray.init()`
  needs no address because the sidecar's session is local to the pod; and the space
  joins as a **zero-compute node**, so it appears in `ray status` and in
  `ray.nodes()` but never receives tasks. Verified: 4 nodes alive, 6.0 cluster CPU,
  9 tasks distributed 3/3/3 across the three real nodes.

- **The space form's default vCPU request cannot be scheduled.** The Create space
  form offers `CPU (Max vCPUs: 4, Max Memory: 16 GiB)` and defaults to 2 vCPUs, but
  `ml.m5.xlarge` with `ThreadsPerCore: 1` has **1930m allocatable**, so a 2-vCPU pod
  is unschedulable on every node. Add the sidecars (250m Ray, 100m SSM) on top. The
  instance-type figure in that dropdown is not what the scheduler sees.

- **Task governance changes what a valid `RayCluster` looks like, and the Ray chapter
  never mentions a label.** This is the most expensive undocumented thing found so
  far. In a governed namespace there are three states, verified 2026-10-06:

  | Labels | Result |
  |---|---|
  | none | creation **refused** by `ValidatingAdmissionPolicy hyperpod-task-governance-admission-policy` |
  | on the `RayCluster` only | **admitted, then stuck forever** |
  | on the `RayCluster` and both pod templates | works |

  The middle state is the dangerous one. Kueue reserves quota and reports
  `QuotaReserved: True` / `Admitted: True`, while the `RayCluster` stays `suspended`
  and `FailedToCreateHeadPod` repeats in the events — the admission policy's
  `resourceRules` also cover `pods`, `deployments` and `statefulsets`, and KubeRay's
  generated pods inherit no labels. Its only exclusion is HPTO-owned objects, via
  `matchConditions`. So the governance layer admits the workload while the admission
  layer refuses its pods, and every obvious check reports health.

  Corollary worth recording: `manageJobsWithoutQueueName: false` in the Kueue config
  does **not** mean unlabelled workloads run unmanaged, because the admission policy
  rejects them before Kueue is consulted.

- **Governance is scoped by namespace labels, not cluster-wide.** The policy binding
  matches `sagemaker.amazonaws.com/activate-quota: Enabled` and
  `sagemaker.amazonaws.com/sagemaker-managed-queue: "true"`, which only the generated
  `hyperpod-ns-*` namespaces carry. Workloads in `default` were unaffected by
  installing the add-on. The chapter's "a workload in a namespace with no allocation
  stays pending and is never admitted" reads like a global switch and is not one —
  this session drained its cluster before installing on the strength of that
  sentence, unnecessarily.

- **Compute allocations generate their namespace; you cannot target an existing
  one.** Team `ray` produces `hyperpod-ns-ray`, and everything else is derived too:
  `hyperpod-ns-<team>-clusterqueue`, `hyperpod-ns-<team>-localqueue`, and priority
  classes with `-priority` appended to the names typed into the cluster policy. The
  namespace appears in neither the `CreateComputeQuota` request nor its response, so
  automation must trust the undocumented convention or discover it afterwards. This
  directly contradicts the chapter's "create an allocation for every namespace where
  you create Ray workloads", which reads as pointing allocations at namespaces you
  already have.

- **Quota is reported in nominal vCPUs, but Topology Aware Scheduling stops it
  causing bad admissions.** 4 × `ml.m5.xlarge` became `cpu nominalQuota: 16`, against
  **7720m** actually allocatable across those four `ThreadsPerCore: 1` nodes — so the
  number you plan an allocation against is double the truth. The tempting conclusion,
  that governance admits workloads Kubernetes cannot place, was **tested and is
  false**: Kueue runs with `TopologyAwareScheduling: true` and a `hyperpod-default`
  topology, which checks real node capacity. A head pod requesting 2 CPU (inside the
  quota, impossible on a 1930m node) is held at the Kueue layer with
  `QuotaReserved: False` and the message *"topology 'hyperpod-default' doesn't allow
  to fit any of 1 pod(s). Total nodes: 4; excluded: resource 'cpu': 4"*.

  Recorded with the correction because the inference was written down before being
  checked, and checking changed the severity from a real failure mode to a
  presentational one. The `ThreadsPerCore` nominal-vs-allocatable gap still bites
  elsewhere, where nothing re-checks — notably the Create space form's 2-vCPU default,
  which produces a genuinely unschedulable pod.

- **Gang scheduling ships disabled, and is not configurable.** The add-on sets
  `DisableWaitForPodsReady: true` in `kueue-manager-config`, and the console's
  Policies tab agrees (`Gang scheduling: Disabled`) — while the Ray chapter instructs
  the reader to *"confirm that gang scheduling is enabled"*. Neither surface exposes
  it: `aws eks describe-addon-configuration` returns an empty schema
  (`additionalProperties: false`, no properties), and the SageMaker API's
  `SchedulerConfig` carries only `PriorityClasses` and `FairShare`. The timeout is
  not exposed either, which matters because `waitForPodsReady` evicts and requeues a
  workload whose pods are not all ready in time, and the default space image takes
  160s to pull cold.

- **The add-on installs Kueue and nothing else.** 11 `kueue.x-k8s.io` CRDs, the
  `kueue-system` namespace and `kueue-controller-manager` — and zero ClusterQueues,
  LocalQueues, ResourceFlavors or WorkloadPriorityClasses until a cluster policy and
  a compute allocation are created. Kueue version 0.19.2 under add-on
  `v1.6.1-eksbuild.1`. The integration list covers `ray.io/raycluster` and
  `ray.io/rayjob` alongside the kubeflow frameworks, plus `pod`, `deployment`,
  `statefulset` and `leaderworkerset`.

- **Spaces work in a task-governed namespace, and the Spaces controller adds the
  Kueue label itself.** Verified 2026-10-06 on `hyperpod-ns-ray`. This is the
  asymmetry that makes the `RayCluster` label requirement so easy to miss: on one
  cluster, under one admission policy, the Spaces controller labels the pods it
  creates and KubeRay does not. A space came up with no manual labelling, registered
  as a Kueue **`pod`** workload (`pod-workspace-…`, distinct from
  `raycluster-…`), and consumed the team's quota: `cpu` went 1500m → 2600m on
  creation (workspace 1000m + ssm-agent 100m) → 2850m after attaching
  (ray-sidecar 250m). Attaching restarts the pod, so its workload is recreated and
  **re-admitted** — which would block on a team near its allocation.

  Two practical consequences: a space cannot change namespace, so a governed setup
  needs a *new* space in `hyperpod-ns-<team>` rather than a restart of one in
  `default`; and the Create space form drops the `Task governance is not enabled for
  this namespace` warning in favour of an Allocations / Utilization panel, which is
  how you can tell the namespace is recognised.

- **Governance changes admission and nothing else.** With the space attached to a
  governed `RayCluster`, `ray.init()` connected, reported 4 nodes alive and 6.0
  cluster CPU, and 9 tasks distributed 4/3/2 across the three real nodes with the
  space contributing none — identical to the ungoverned run. Remote IDE access also
  behaved identically: the space registered as an Online SSM managed instance and an
  `AWS-StartSSHSession` session connected from local VS Code.

- **The console's namespace Utilization panel truncates to whole vCPUs.** With
  `cpu=1500m` consumed by Kueue's accounting, the Create space form showed
  `Allocated vCPUs 0`. So a namespace running a Ray cluster reads as having nothing
  allocated, on the form where a user decides how much to request.

## Proposed edits to the main doc

### 1. Hung job detection has a node AMI floor

**Where:** wherever hung job detection lands (candidate
`mental-model/hyperpod-ray.md`); the extracted chapter's "Hung job detection"
section states no version floor at all.

**DO NOT MERGE YET — the mechanism is contradicted. See the investigation
below.** Kept here because the *symptom* is reproducible and worth tracking, but
the explanation is not established.

**Gap:** the chapter says "all Ray Train workers on HyperPod are monitored using
platform defaults with no code changes required", which reads as
unconditional. The console contradicts that with a hard `AMI out of date`
status and the action "Update AMI to Aug 18, 2026 or newer".

**What we tested (2026-10-05):** the obvious reading — old cluster, old AMI — is
**false**. `k8-ray-3`, created 2026-10-05 from the current cluster-setup assets,
reports `AMI out of date` identically to `k8-1` from 2026-06-15, even though:

- its nodes run `Amazon Linux 2023.12.20260918` (a month past the stated floor),
- their kernel `6.12.103-129.197.amzn2023` is *newer* than the
  `6.12.100-125.179.amzn2023` listed in the **August 29, 2026** EKS AMI release
  notes, i.e. the node is on an AMI newer than the newest documented release, and
- **the cluster's own AMI status in the console reads `Up to date`.**

So the console contradicts itself: only this one row in the Ray features table
claims the AMI is stale. Either the row means something other than what it says
(most likely: the on-node component does not exist in any released AMI yet, and
the row is a stand-in for "not available"), or it is a bug.

Also worth recording as a capability gap: **there is no customer-visible field to
check a node's HyperPod AMI version against a date.** HyperPod instances live in
a service-managed account (`aws ec2 describe-instances` on a node's instance ID
returns `InvalidInstanceID.NotFound`), and neither `describe-cluster-node` nor the
Kubernetes node object exposes an `ImageId` or AMI version. `osImage` and
`kernelVersion` are the only proxies.

**Proposed wording, once the mechanism is known:** hold. If the component is
genuinely AMI-gated, say so with the real signal. Do not write "requires an AMI
from 2026-08-18 or later" into the mental model — that sentence is what we just
failed to confirm.

### 2. ~~The AMI floor maps to the August 29, 2026 EKS AMI release~~ (withdrawn)

**Withdrawn 2026-10-05**, same day it was written. The reasoning was that the
documented EKS AMI releases bracket the 2026-08-18 floor without hitting it
(**July 30, 2026** and **August 29, 2026**, nothing between), so the August 29
release must be the first qualifying one. The test that should have confirmed it
falsified the premise instead: a cluster on an AMI newer than the August 29
release still reports `AMI out of date`. See finding 1.

One observation from this line of investigation survives and is worth keeping:
the AMI release notes list only package inventories (kernel, NVIDIA driver, CUDA,
EFA, containerd, …) and **never mention hung job detection or any job-monitoring
agent**. So even if the dependency is real, it is invisible from the AMI side —
there is nothing in the release notes to match a requirement against.

### 3. Two supported ways to install KubeRay

**Where:** alongside the existing "KubeRay has no EKS add-on" note.

**Proposed wording:** There is exactly one way KubeRay reaches a HyperPod
cluster: a Helm install of the upstream chart. It is not an EKS managed add-on,
it does not appear in `aws eks list-addons`, and the console's Ray panel does not
install it — the panel's `Install` button opens the documentation for the Helm
procedure. What you choose is only *who runs Helm*: you by hand, or a
Helm-capable custom resource such as
`hyperpod_ray/cfn/kuberay-operator.yaml`, which additionally pins the chart
version and makes the install reproducible.

## Confirmations (the chapter held under test)

The 2026-10-05 revision of the SageMaker AI Developer Guide PDF was extracted
(pages **2805-2870**, up from 2784-2849 as the guide grew 9397 → 9468 pages) and
diffed against the 2026-09-09 extraction:

1. **The Ray chapter did not change at all in ~4 weeks.** The two extractions are
   byte-identical apart from the provenance header line. So the console's Ray
   panel, its per-feature readiness table, and the hung-job-detection AMI floor
   are all **undocumented**, not merely documented somewhere else in the guide.
   The chapter's bookmark structure is also unchanged — no sections added,
   removed, or renamed.

2. **Guide-wide, the HyperPod additions in this revision are elsewhere.** Diffing
   the two PDFs' bookmark trees, the new material is: *Migrating to API-driven
   Slurm configuration* (a large new section, including a field-mapping reference
   and the removal of `provisioning_parameters.json` from S3), *Inference Gateway
   for HyperPod Inference* (a new add-on, its `InferenceGatewayConfig` CRD
   reference, and a troubleshooting guide), *Instance preference lists* for
   processing and training jobs, and a benchmarking section for custom
   tokenizers from S3. The Inference release-note bookmarks were also renamed to
   carry both the EKS add-on build and the operator version
   (e.g. "HyperPod Inference Amazon EKS v2.1.0-eksbuild.1 and Inference Operator
   v3.7"). Nothing Ray-related.

## Not yet verified (kept honest)

- The full contents of the `Install` dropdown. One item was pressed and it opened
  documentation; whether any item performs an install is unknown.
- The contents of the `Actions` dropdown that replaces `Install` once KubeRay is
  present. If it offers upgrade or uninstall, the console can mutate a Helm release
  it did not create.
- What signal the `Hung job detection` row actually reads. Everything
  customer-visible says the AMI is current, including the console's own AMI
  status, so the row is reading something else or nothing at all.
- Whether hung job detection works *despite* the row — i.e. whether the status is
  cosmetic. Not tested; it would need a deliberately hung Ray Train job.

## Open questions

- ~~Does the console Ray install supersede the `hyperpod_ray/` CloudFormation
  stack?~~ **Answered: no.** There is no console install to supersede it. The
  stack remains the only non-manual way to land KubeRay on a cluster.
- Is there a non-console API for these add-ons at all (CloudFormation
  `AWS::EKS::Addon` covers the five catalog add-ons, but not Ray)?
