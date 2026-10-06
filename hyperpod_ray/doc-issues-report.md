# Ray on SageMaker HyperPod — documentation and console issues

Findings from setting up Ray on HyperPod end to end through the console on
2026-10-05, following the SageMaker AI Developer Guide. Every item below was
reproduced on a cluster created the same day from the current official
cluster-setup assets, and each one cost time that the documentation could have
saved.

**Environment.** HyperPod cluster `k8-ray-3` (EKS orchestration, `Continuous`
provisioning), EKS `1.34`, us-west-2. Created from
`s3://aws-sagemaker-hyperpod-cluster-setup-us-west-2-prod/1/templates/main-stack-eks-based-template.yaml`.
KubeRay 1.7.1 by Helm. Spaces add-on `v0.2.0-eksbuild.2`. Node AMI
`Amazon Linux 2023.12.20260918`, 4 × `ml.m5.xlarge` with `ThreadsPerCore: 1`.

Issues are grouped by the page or surface that needs the change. Severity is
about time lost, not about data risk: **High** sent us down a wrong path, **Medium**
caused a silent failure, **Low** is a factual correction.

---

## 1. Console: a 403 is reported as a missing CRD

**Severity: High.** This is the single most expensive issue in the list.

**Surface:** Studio → HyperPod cluster → **Tasks** tab.

**What happens.** When the domain execution role cannot reach the Kubernetes API,
the Tasks tab shows:

> The Custom Resource Definition (CRD) of type PyTorch - Kubeflow training operator
> is not configured on the cluster. Note that tasks will only be visible once the
> CRD is correctly configured.

**What is actually true.** The CRD exists. `kubectl get crds` listed
`pytorchjobs.kubeflow.org` and all four `ray.io` CRDs. Every request was returning
403 because the execution role lacked `eks:AccessKubernetesApi`.

**Why it is expensive.** The message names cluster configuration, so that is where
you look. In order, we checked whether the CRD existed, whether the HyperPod Helm
chart was too old, and whether the cluster-access policies were scoped wrongly —
three dead ends — before finding an IAM permission. The permission *is* documented
(issue 3), but nothing in the error points at IAM.

A secondary symptom compounds it: with every request refused, changing the **Task
type** dropdown appears to do nothing and the error banner keeps naming the
previous task type. That reads as a UI bug and sends you looking in another wrong
direction.

**Suggested fix.** Distinguish the two cases. If the API call returns 403, say so
and name the likely cause — for example *"Access denied reading
pytorchjobs.kubeflow.org. Check that the execution role has
eks:AccessKubernetesApi and that cluster access is granted."* The mechanism for
telling them apart is already available: the UI's own feature detection uses
`apiextensions.k8s.io/customresourcedefinitions get` and
`authorization.k8s.io/selfsubjectaccessreviews create`, both granted by
`AmazonSagemakerHyperpodUserClusterPolicy`.

---

## 2. Following the Ray chapter produces a space that cannot use its cluster

**Severity: High.** The warning is in the documentation. It is on a different page
from the example that violates it.

**Where each half comes from.** Two sibling pages both have a section called
**Creating a cluster**. One carries the warning; the other carries the manifest that
ignores it.

| Page | Section | Content |
|---|---|---|
| `sagemaker-hyperpod-ray-manage-studio.html` | *Creating a cluster* | *"A space carries its own Ray version, from the SageMaker AI Distribution image it runs. Match that version to the Ray version of the cluster. A mismatch produces runtime errors that are hard to diagnose."* |
| `sagemaker-hyperpod-ray-manage-kubectl.html` | *Creating a cluster* | `image: rayproject/ray:2.55.1`, with no mention of spaces or version matching |
| `sagemaker-hyperpod-ray-deploy-model.html` | *A RayService manifest* | `image: rayproject/ray:2.56.1` |
| `sagemaker-hyperpod-ray-attach-space.html` | *Version compatibility* | restates the requirement, and recommends the same Distribution image on both sides |

A reader who creates clusters with `kubectl` — which is the path this walkthrough
took, and the path anyone doing IaC takes — sees the manifest and never the warning.
The two sections share a heading, so there is no cue that the Studio page says
something the kubectl page omits. And `attach-space.html`, where the requirement is
stated most fully, carries no `RayCluster` manifest at all: the page that states the
rule is not the page a reader copies from.

**The space side is not a documented instruction.** The documentation never names an
image or tag for a space — it only refers to *"the space's SageMaker AI Distribution
image"* as a given. `sagemaker-distribution:latest-cpu` comes from the Spaces add-on's
own installed templates:

```console
$ kubectl get workspacetemplates -n jupyter-k8s-system     -o jsonpath='{range .items[*]}{.metadata.name}  {.spec.defaultImage}{"\n"}{end}'
sagemaker-code-editor-template  public.ecr.aws/sagemaker/sagemaker-distribution:latest-cpu
sagemaker-jupyter-template      public.ecr.aws/sagemaker/sagemaker-distribution:latest-cpu
```

and the Create space form pre-fills it. So the collision is between a **documented
example** and a **product default** — which is worse than two conflicting documents,
because the reader has no reason to suspect the default.

**What happens.** Create a `RayCluster` from the chapter's example manifests, create
a space from the default template, attach them. The Connect dialog accepts the
pairing with **no warning**, the Ray cluster tab reports **`Connected`**, and then:

```
RuntimeError: Version mismatch: The cluster was started with:
    Ray: 2.55.1
    Python: 3.10.20
This process on node 10.1.151.109 was started with:
    Ray: 2.55.1
    Python: 3.12.14
```

**Where it comes from.**

| Side | Where the image comes from | Python |
|---|---|---|
| `RayCluster` | the documented example in *Creating a cluster* (kubectl) | 3.10.20 |
| Space | the add-on's default template, pre-filled in the form | 3.12.14 |

The **Ray versions match** at 2.55.1, which is exactly why this is easy to walk
into. The chapter does state the requirement — *"The Python version must match as
well, including the patch version"* — twice, and recommends the same Distribution
image on both sides. Neither statement is anywhere near the manifest a reader
copies.

**Suggested fix.** Put the warning where the manifest is. Either use a SageMaker
Distribution image in the kubectl *Creating a cluster* example, or add the
version-matching note to that section as well — it already exists verbatim on the
Studio page one level away. Pinning by digest rather than `latest-cpu` would also
help, since a moving tag on one side and a fixed tag on the other reintroduces the
drift later. Pinning by digest rather than
`latest-cpu` would also help, since `latest` on one side and a fixed tag on the
other reintroduces the drift later.

### 2a. Studio does not warn, contrary to the documentation

**Severity: High.** Same page.

**What the docs say.** *"When the versions differ, Studio shows a warning and offers
to create a compatible cluster instead."*

**What happens.** On Spaces add-on `v0.2.0-eksbuild.2`, the **Connect Ray cluster**
dialog listed the incompatible cluster normally, offered no warning, and saved
successfully. The `Create new Ray cluster` button is present unconditionally, not
as a remedy offered on mismatch. The validation appears to compare `rayVersion`
only, which matched.

`Connected` is then shown for a pairing that cannot work. The status is accurate
about something narrower than a user reads it as: the space pod really does join the
cluster, and the injected `ray-sidecar` cannot mismatch because it runs the
cluster's own head image. Only the user's Python process is refused — three console
screens later.

**Suggested fix.** Compare Python as well as Ray, and either warn or do what the
documentation already promises. Failing that, correct the documentation.

---

## 3. The critical IAM requirement is reachable but not where failures point

**Severity: Medium.**

**Page:** `sagemaker-hyperpod-studio-setup-eks.html` — which is correct, and
contains the full policy including:

```json
{
  "Sid": "UseEksClusterPermissions",
  "Action": ["eks:DescribeCluster", "eks:AccessKubernetesApi", "eks:MutateViaKubernetesApi"],
  "Resource": "arn:aws:eks:<region>:<account>:cluster/<eks-cluster-name>"
}
```

**The problem is navigation, not content.** The Ray chapter's Studio section refers
to this page as *"Setting up an Amazon EKS cluster"*, which does not read like
"the page with the IAM policy you cannot work without". Combined with issue 1,
where the failure points at cluster configuration, the requirement is easy to miss
entirely.

Worth stating explicitly somewhere prominent: **`AmazonSageMakerFullAccess`
contains no `eks:` actions at all.** We verified this by searching its 24 KB policy
document. A role built from that managed policy alone cannot reach the cluster, no
matter what cluster access has been granted.

**Suggested fix.** In the Ray chapter's Studio prerequisites, name the IAM policy
requirement inline rather than only by link, and state the
`AmazonSageMakerFullAccess` gap.

---

## 4. `AmazonSagemakerHyperpodSpaceTemplatePolicy` names the wrong namespace

**Severity: Medium** — it fails silently.

**Page:** `sagemaker-hyperpod-studio-setup-eks.html`, cluster-access policy table.

**What the docs say.** *"Attach it scoped to the `jupyter-k8s-shared` namespace,
where the templates live."*

**What is actually true.** On Spaces add-on `v0.2.0-eksbuild.2`:

```console
$ kubectl get workspacetemplates -A
NAMESPACE            NAME                             APP TYPE
jupyter-k8s-system   sagemaker-code-editor-template   Code Editor
jupyter-k8s-system   sagemaker-jupyter-template       JupyterLab

$ kubectl get ns jupyter-k8s-shared
Error from server (NotFound): namespaces "jupyter-k8s-shared" not found
```

The access strategy and the `ray-integration` integration template are also in
`jupyter-k8s-system`. Scoping an EKS access policy to a namespace that does not
exist is accepted by the API and grants nothing, so following the documentation
produces a policy that silently does nothing.

**Suggested fix.** Correct the namespace, or document both if user-created shared
templates are expected to live in `jupyter-k8s-shared`.

---

## 5. Troubleshooting command names a namespace that does not exist

**Severity: Low**, but it blocks the first troubleshooting step.

**Page:** `vscode-access.html`, Troubleshooting.

**What the docs say.** *"SageMaker Spaces add-on is running:
`kubectl get pods -n sagemaker-spaces-system`"*

**What is actually true.** That namespace does not exist. The controller runs in
`jupyter-k8s-system`:

```console
$ kubectl get pods -n jupyter-k8s-system
NAME                                              READY   STATUS
jupyter-k8s-controller-manager-76b675d7d9-qfr9c   2/2     Running
```

This is the second wrong namespace in the Spaces documentation, after issue 4.

---

## 6. The space's "Remote access" toggle links to documentation for a different product

**Severity: Medium.**

**Surface:** Studio → space → **Settings** → **Remote access**, whose *Learn more*
points at `remote-access.html`.

**What that page documents.** Classic SageMaker Studio spaces, which are
instance-based. It specifies instance types (*"`ml.t3.medium`, `ml.c7i.large` …
are not supported due to insufficient memory"*), an **Instance requirements**
section, and links to `studio-updated-spaces.html`. None of that applies to a
HyperPod space, which runs as a pod.

The HyperPod path is a different series — `access-mechanism.html` →
`vscode-access.html` — and **that series never mentions a per-space toggle**. It
says to enable remote access when installing the add-on, which the add-on panel
reports as `Remote access: Enabled`.

**Compounding this, the toggle appears not to matter.** With the space-level toggle
reading **`Off`** and the console's own `Open in VS Code` button greyed out, remote
access worked:

- the space's `accessStrategy` already referenced `hyperpod-access-strategy`, which
  carries `createConnectionContext: {port: "2222", ssmDocumentName: "AWS-StartSSHSession"}`
  and handlers for `vscode-remote`, `cursor-remote` and `kiro-remote`;
- the `ssm-agent-sidecar` container was running;
- the space was registered as an **Online** SSM managed instance;
- a `WorkspaceConnection` returned a usable URL, and connecting from VS Code
  succeeded.

**Suggested fix.** Point the link at `access-mechanism.html`, and document what the
per-space toggle controls — or remove it from the HyperPod space UI if it is
inherited from classic Studio and has no effect here.

---

## 7. The easiest connection method has no instructions

**Severity: Low.**

**Page:** `remote-access.html` lists *"AWS Toolkit for Visual Studio Code"* as one of
three connection methods, with no steps. `vscode-access.html` documents only the
`WorkspaceConnection` / `hyp create hyp-space-access` route.

**What works and is simpler.** The AWS Toolkit's Explorer tree lists HyperPod spaces
directly — `AWS → Explorer → <region> → SageMaker AI → HyperPod → <space>` — and
connects in one click, with no URL to generate and no `kubectl`. For reference, what
it sets up locally:

```
# ~/.ssh/config, written by the Toolkit
Host smhp_*
    ProxyCommand '…/globalStorage/amazonwebservices.aws-toolkit-vscode/hyperpod_connect' '%h'
```

with host names of the form
`smhp_lc_<space>_<namespace>_<eks-cluster>_<region>_<account>`, and the resulting
SSM session owned by the space controller role, not by the user:

```console
$ aws ssm describe-sessions --state Active
Doc:    AWS-StartSSHSession
Target: mi-02cfcb86ceabcfb7e
Owner:  …assumed-role/sagemaker-space-Controller-20261005T163975/…
```

**Suggested fix.** Document the Toolkit tree route as the primary path, since it is
the shortest and the one most users will find.

---

## 8. `--template-url` in the CloudFormation instructions does not resolve

**Severity: Low**, but the given command cannot work.

**Page:** `smcluster-getting-started-eks-console-create-cluster-cfn.html`.

**What the docs give.**

```
--template-url https://aws-sagemaker-hyperpod-cluster-setup.amazonaws.com/templates-slurm/main-stack-slurm-based-template.yaml
```

**What happens.** The host does not exist:

```console
$ host aws-sagemaker-hyperpod-cluster-setup.amazonaws.com
Host aws-sagemaker-hyperpod-cluster-setup.amazonaws.com not found: 3(NXDOMAIN)
```

A regional S3 URL does work, for contrast:

```console
$ curl -s -o /dev/null -w '%{http_code}\n' \
    https://aws-sagemaker-hyperpod-cluster-setup-us-west-2-prod.s3.us-west-2.amazonaws.com/1/templates/main-stack-eks-based-template.yaml
200
```

Two smaller problems on the same page: it is reached from the **EKS** cluster
creation flow but the example URL is the **Slurm** template
(`templates-slurm/main-stack-slurm-based-template.yaml`), and step 1 links to the
Slurm console tutorial.

---

## 9. The KubeRay install command is unpinned and lands in `default`

**Severity: Medium.**

**Page:** `sagemaker-hyperpod-ray-install-kuberay.html`.

**What the docs give.**

```bash
helm install kuberay-operator kuberay/kuberay-operator
```

**Two problems.** No `--version`, so it resolves to whatever is latest — on
2026-10-05 that was chart 1.7.1. And no namespace, so a **cluster-wide operator
lands in `default`**, sharing a namespace with user workloads and making
`kubectl get all -n default` unusable. The upstream KubeRay documentation that this
page links to does use a dedicated namespace.

The page also does not mention a minimum version, although other parts of the same
chapter depend on one: `RayCronJob` does not exist before KubeRay 1.6.0, and Ray's
Kubernetes RBAC auth mode requires 1.6 or later.

**Suggested fix.**

```bash
helm install kuberay-operator kuberay/kuberay-operator \
  --namespace kuberay-operator --create-namespace --version <pinned>
```

and state the ≥ 1.6.0 floor.

---

## 10. `Hung job detection` reports `AMI out of date` on a current AMI

**Severity: Medium. Unresolved — we could not determine the signal.**

**Surface:** cluster → Ray add-on panel → **Ray features** table.

**What happens.** The row reads `AMI out of date` with the action *"Update AMI to
Aug 18, 2026 or newer"*, on a cluster created 2026-10-05 whose AMI status elsewhere
in the console reads **`Up to date`**.

**Evidence that the node is not stale.**

| Signal | Value |
|---|---|
| `osImage` | `Amazon Linux 2023.12.20260918` — a month past the stated date |
| `kernelVersion` | `6.12.103-129.197.amzn2023` |
| Kernel in the **August 29, 2026** EKS AMI release notes | `6.12.100-125.179.amzn2023` — *older* |
| Cluster AMI status in the console | `Up to date` |

The same row appeared on a second cluster created 2026-06-15, so it is not
age-dependent in the obvious way. Either the row reads a signal other than the AMI
(perhaps an on-node component not yet shipped in any AMI, in which case the wording
is misleading), or it is a bug.

**A related gap:** there is no customer-visible way to check a node's HyperPod AMI
version against a date. HyperPod instances are in a service-managed account, so
`aws ec2 describe-instances` on a node's instance ID returns
`InvalidInstanceID.NotFound`, and neither `describe-cluster-node` nor the Kubernetes
node object exposes an `ImageId` or AMI version. `osImage` and `kernelVersion` are
the only proxies.

---

## 11. Smaller observations

**`Quick Install` is not "latest".** It installed `amazon-sagemaker-spaces`
`v0.2.0-eksbuild.2` while the catalog offered `v0.2.1-eksbuild.1`. It clears the
≥ 0.2.0 floor Ray interactive development needs, but the wording invites the
assumption that it is current. Worth documenting that it pins a tested version.

**The Create space form's default vCPU request cannot be scheduled.** The form
offers `CPU (Max vCPUs: 4, Max Memory: 16 GiB)` and defaults to **2 vCPUs**, but an
`ml.m5.xlarge` with `ThreadsPerCore: 1` has **1930m allocatable**, so a 2-vCPU pod is
unschedulable on every node and sits `Pending` indefinitely. The two sidecars
(250m Ray, 100m SSM) come on top. The figure in that dropdown is the instance
type's nominal vCPU count, not what the scheduler sees.

**SSM managed instances leak when spaces are deleted.** 26 registrations existed on
this account, 24 of them `ConnectionLost` remnants of deleted spaces. Nothing
appears to deregister them.

**Spaces documentation is split across two namespaces of its own making.** Issues 4
and 5 are both wrong-namespace errors in the Spaces material, which suggests the
docs were written against an earlier layout.

**A VS Code annoyance after connecting.** On first connection the Python extension
reports *"An Invalid Python interpreter is selected"* even though the notebook
kernel works at Python 3.12.14. IntelliSense and linting are off until the user
picks `/opt/conda/bin/python` manually. Worth a line in the remote-IDE setup page.

---

## 12. A governed `RayCluster` needs Kueue labels in three places, and none are documented

**Severity: High.** One of the three states fails silently and looks healthy.

**Page:** `sagemaker-hyperpod-ray-task-governance.html` and its child *Setting up
task governance for Ray*. Neither mentions `kueue.x-k8s.io/queue-name`, or any
label. Searching the whole Ray chapter for `queue-name` or `kueue` returns only an
aside about `waitForPodsReady` and a mention of Kueue as a metrics source.

**What is actually required.** In a namespace under task governance, the label must
appear on the `RayCluster` **and on both pod templates**. The three outcomes:

| Labels | Result |
|---|---|
| none | **Creation refused.** `ValidatingAdmissionPolicy 'hyperpod-task-governance-admission-policy' denied request: The label 'kueue.x-k8s.io/queue-name' is either missing or does not have a value set.` Clear and actionable. |
| on the `RayCluster` only | **Accepted, then stuck forever.** See below. |
| on the `RayCluster` and both pod templates | Works. |

**The middle case is the problem.** Kueue admits the workload and reserves quota, so
every obvious check reports success. The admission policy's `resourceRules` also
cover `pods`, and KubeRay's generated pods inherit no labels, so each pod creation is
denied and retried forever:

```console
$ kubectl get workload -n hyperpod-ns-ray
NAME                            ADMITTED
raycluster-ray-governed-0ded7   True

$ kubectl get raycluster -n hyperpod-ns-ray
NAME            STATUS
ray-governed    suspended

$ kubectl get events -n hyperpod-ns-ray
Warning  FailedToCreateHeadPod  pods "ray-governed-head-4hh4r" is forbidden:
  ValidatingAdmissionPolicy … denied request: The label
  'kueue.x-k8s.io/queue-name' is either missing or does not have a value set.
```

The Kueue `Workload` says `QuotaReserved: True` and `Admitted: True`. The
`RayCluster` says `suspended`. The cause is only in the events. The governance layer
admits the workload while the admission layer refuses its pods.

**Suggested fix.** Document the labels, with the pod templates called out
explicitly, in *Setting up task governance for Ray* — a worked manifest would be
best, since this is exactly the kind of thing readers copy. Alternatively have the
admission policy exempt pods owned by a `RayCluster` whose own labels are correct,
the way it already exempts HPTO-owned objects via `matchConditions`. That would
reduce the three states to two, and remove the one that lies.

---

## 13. Gang scheduling is off by default, the docs say to verify it is on, and it cannot be configured

**Severity: Medium.**

**Page:** *Setting up task governance for Ray*:

> **Confirm that gang scheduling is enabled for your cluster.** A Ray cluster needs
> its head and all of its workers running together, so without gang scheduling a
> partially scheduled cluster holds capacity without making progress. Task
> Governance implements gang scheduling with the Kueue `waitForPodsReady` feature…
> For the configuration settings, see the section called "Gang scheduling".

**What is actually true.** The add-on ships it disabled, and the console agrees:

```console
$ # Policies tab
Gang scheduling: Disabled

$ kubectl get cm kueue-manager-config -n kueue-system -o yaml | grep -A2 featureGates
featureGates:
  DisableWaitForPodsReady: true
```

**And there is no way to change it.** The EKS add-on publishes an empty
configuration schema:

```console
$ aws eks describe-addon-configuration --addon-name amazon-sagemaker-hyperpod-taskgovernance \
    --addon-version v1.6.1-eksbuild.1 --query configurationSchema
{"$schema":"…","additionalProperties":false,"description":"Amazon SageMaker HyperPod task governance","type":"object"}
```

and the SageMaker API's `SchedulerConfig` carries only `PriorityClasses` and
`FairShare` — no gang scheduling, no `waitForPodsReady` timeout. So the reader is
told to verify a setting that is off, pointed at a section for "the configuration
settings", and given no API that exposes it.

The timeout matters in practice: `waitForPodsReady` evicts and requeues a workload
whose pods are not all ready in time, and the default space image
(`sagemaker-distribution`) takes **160 seconds** to pull on a cold node. If gang
scheduling is enabled with a short timeout, Ray clusters would enter an
eviction/requeue loop on first start.

---

## 14. Compute allocations cannot target an existing namespace

**Severity: Medium.** The documentation implies the opposite.

**Page:** *Setting up task governance for Ray*:

> Task Governance admits a Ray workload only in a namespace that has a compute
> allocation. **Create an allocation for every namespace where you create Ray
> workloads.**

**What is actually true.** The Create compute allocation form states:

> Namespace will be **auto-generated** based on the defined team name.

Team `ray` produces namespace `hyperpod-ns-ray`. There is no field for an existing
namespace, so `default` — or any namespace you already use — cannot be governed from
the console. The instruction reads as "point allocations at your namespaces"; the
reality is "the allocation creates the namespace, move your workloads there".

**Also undocumented: the derived names.** Everything is generated from the team
name, and automation needs all of them:

```
namespace              hyperpod-ns-<team>
ClusterQueue           hyperpod-ns-<team>-clusterqueue
LocalQueue             hyperpod-ns-<team>-localqueue
WorkloadPriorityClass  <name-you-typed>-priority
```

The namespace is not in the `CreateComputeQuota` request or response, so anything
automating this must either trust the undocumented convention or discover the
namespace afterwards.

**One thing the docs get right but state too weakly.** "A workload in a namespace
with no allocation stays pending and is never admitted" reads like a cluster-wide
switch, and it is not: the admission policy binding is scoped by namespace labels
(`sagemaker.amazonaws.com/activate-quota: Enabled` and
`sagemaker.amazonaws.com/sagemaker-managed-queue: "true"`). Workloads in ungoverned
namespaces are unaffected. Saying so would save people from draining clusters before
installing the add-on, as we did.

---

## 15. Quota counts nominal vCPUs, not what the scheduler can place

**Severity: Medium.**

An allocation of 4 × `ml.m5.xlarge` produced:

```console
$ kubectl get clusterqueue hyperpod-ns-ray-clusterqueue -o yaml
  cpu     nominalQuota: 16     borrowingLimit: 8
  memory  nominalQuota: 64Gi   borrowingLimit: 32Gi
```

16 CPU is 4 vCPU × 4 instances, the instance type's nominal figure. The nodes in
question run with `ThreadsPerCore: 1` and report **1930m allocatable each — 7720m
total**. Quota is therefore more than double real capacity, and a workload can be
admitted by governance and then sit `Pending` because Kubernetes has nowhere to put
it: two layers with two different ideas of how large the cluster is.

This compounds the `ThreadsPerCore` trap that already exists elsewhere (the Create
space form's 2-vCPU default, issue 11). A note in the task governance documentation
that quota is accounted in nominal vCPUs — and that SMT-disabled instance groups
offer about half that — would prevent a confusing class of `Pending`.

---

## 16. `Quick Install` is not latest, again

**Severity: Low**, but now a pattern.

Task governance `Quick Install` chose `v1.6.1-eksbuild.1` while the catalog offered
`v1.6.1-eksbuild.2`. The Spaces add-on did the same (issue 11). The two panels are
also inconsistent about telling you: task governance shows *"A new version is
available for this add-on"* with an `Update version` button, Spaces shows nothing.

Task governance also installs no confirmation dialog enumerating what it creates,
where the Spaces add-on does — a dialog that was genuinely useful. Worth aligning.

---

## What worked well, for balance

Several things were better than expected and are worth preserving:

- **The Ray add-on panel reads real cluster state.** It reported `Installed` after a
  KubeRay install done entirely by hand with Helm into a dedicated namespace, with
  no console involvement. Its `Ray features` rows likewise track actual add-on
  presence — the task-governance row differed correctly between two clusters.
- **The Spaces add-on confirmation dialog enumerates what it will create** — three
  IAM roles, SSM connectivity, cert-manager and EBS CSI as prerequisites, the
  controller and router — and states plainly that browser access is not configured.
  More console dialogs should do this.
- **`ray.init()` really does work with no arguments**, via injected `RAY_ADDRESS=auto`
  and a sidecar that joins the pod to the cluster as a zero-compute node. Nine tasks
  from a notebook in remote VS Code distributed across the three real nodes while
  the space itself received none, which is the documented intent.
- **Ray's own `check_version_info()` fails loudly and precisely** on the version
  mismatch in issue 2. Given that the console let it through, this is the only thing
  that made the problem diagnosable at all.
