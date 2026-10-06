# Ray on HyperPod - setup

Sets up a **Ray on SageMaker HyperPod** environment: the KubeRay operator by
Helm, and a SageMaker AI domain by CloudFormation.

Ray on HyperPod is an official HyperPod feature. It runs the upstream, unmodified
open source Ray and KubeRay, and HyperPod adds capabilities around them
(Studio integration, authenticated dashboard access, task governance queueing,
resilient training, observability). Per the developer guide, the whole baseline
is two things:

1. A HyperPod cluster orchestrated by Amazon EKS.
2. The KubeRay operator installed on it.

This solution covers step 2, plus the optional Studio integration. Step 1 stays
with
[aws/sagemaker-hyperpod-cluster-setup](https://github.com/aws/sagemaker-hyperpod-cluster-setup),
the official cluster setup assets. Keeping them separate makes the iteration loop
fast: you create the cluster once and redo just the Ray part as it grows.

**The console does not install KubeRay.** The SageMaker AI console has gained a
`Ray` add-on panel that reports installation status and a per-feature readiness
table, but its `Install` button opens the documentation. Helm is the only
mechanism. The panel does read real cluster state, so it reports `Installed`
after a Helm or Makefile install it had no part in. See
[console-install-walkthrough.md](console-install-walkthrough.md).

## Contents

| Path | What it is |
|---|---|
| [Makefile](Makefile) | `make install-kuberay` and the domain stack, plus inspection and teardown. `make help` lists every target. |
| [cfn/sagemaker-domain.yaml](cfn/sagemaker-domain.yaml) | SageMaker AI domain, user profile, and the EKS access entry that puts Ray workloads on Studio's Tasks tab. |
| [console-install-walkthrough.md](console-install-walkthrough.md) | Step-by-step record of setting this up through the console, with what each step actually changes and which steps are worth automating. |
| [scripts/capture-cluster-state.sh](scripts/capture-cluster-state.sh) | Read-only snapshot of Helm releases, Ray CRDs, EKS add-ons and access entries. Run before and after a step, then diff. |
| [examples/ray-cluster-cpu.yaml](examples/ray-cluster-cpu.yaml) | A minimal CPU-only `RayCluster` for verifying the setup. The default. |
| [examples/ray-cluster-gpu.yaml](examples/ray-cluster-gpu.yaml) | The same thing with a GPU worker group. |
| [examples/ray-cluster-space.yaml](examples/ray-cluster-space.yaml) | For attaching a SageMaker Studio space. Runs the same SageMaker Distribution image the space does, pinned by digest, because Ray refuses to connect when the driver's Python differs from the cluster's. |
| [examples/ray-cluster-governed.yaml](examples/ray-cluster-governed.yaml) | For a namespace under task governance. Carries the Kueue labels on the cluster **and** both pod templates — labelling only the cluster leaves it `suspended` forever. |
| [examples/rayjob-ephemeral.yaml](examples/rayjob-ephemeral.yaml) | A `RayJob` that creates its own cluster and deletes it afterwards. |
| [examples/rayjob-existing.yaml](examples/rayjob-existing.yaml) | A `RayJob` that runs on a `RayCluster` you already have. |
| [examples/rayservice-serve.yaml](examples/rayservice-serve.yaml) | A `RayService` running the Ray Serve app. |
| [examples/scripts/](examples/scripts/) | The three workloads: Ray Data, Ray Train, Ray Serve. Mounted into the pods as a ConfigMap. |
| [scripts/extract_pdf_docs.py](scripts/extract_pdf_docs.py) | Extracts a page range of an AWS docs PDF to Markdown. |
| `docs/ray-on-hyperpod.md` | The "Ray on SageMaker HyperPod" chapter, extracted for easy reading by humans and agents. Generated locally, not committed. |

## Prerequisites

- A running HyperPod cluster orchestrated by Amazon EKS. The EKS cluster's
  authentication mode must include `API` (`API` or `API_AND_CONFIG_MAP`), which
  is what the official setup assets configure.
- `kubectl` and `helm`, with `kubectl` pointing at the cluster.
- AWS CLI, with permissions to create IAM roles and EKS access entries.

## Quick start

```bash
make kubeconfig EKS_CLUSTER_NAME=my-hyperpod-eks-cluster
make install-kuberay

make operator-status
make crds
```

`make install-kuberay` pins the chart version and installs into a dedicated
namespace, neither of which the documented `helm install kuberay-operator
kuberay/kuberay-operator` does — that command tracks latest and puts a
cluster-wide operator in `default`. It is also safe to re-run, and refuses rather
than conflicting if KubeRay already exists in a different namespace.

`make help` lists every target.

Then verify end to end with a real Ray cluster:

```bash
make deploy-example                      # CPU-only by default
make deploy-example EXAMPLE_FLAVOR=gpu   # needs a GPU instance group with capacity
make list-clusters                       # wait for STATUS ready
make dashboard                           # http://localhost:8265
make delete-example
```

`EXAMPLE_FLAVOR` selects the manifest and the `RayCluster` name together, so
nothing else needs overriding.

Check that the example fits your nodes before applying it, rather than sizing
from the instance type. An instance group with `ThreadsPerCore: 1` runs without
SMT, so its nodes report physical cores - an `ml.m5.xlarge` node shows 2 CPUs,
1930m of it allocatable, where the same type with `ThreadsPerCore: 2` shows 4.
The node labels are identical either way, and a pod asking for more than what is
left stays Pending indefinitely with `Insufficient cpu`:

```bash
kubectl get nodes -o custom-columns=\
'NAME:.metadata.name,CPU:.status.allocatable.cpu,MEM:.status.allocatable.memory'

aws sagemaker describe-cluster --cluster-name <hyperpod-cluster> \
  --query 'InstanceGroups[].{Name:InstanceGroupName,Type:InstanceType,ThreadsPerCore:ThreadsPerCore}'
```

## Example workloads

Three scripts under [examples/scripts/](examples/scripts/) cover the Ray libraries
you are most likely to reach for. Each is heavily commented, runs on CPU only, and
needs nothing that the `rayproject/ray` image does not already have:

| Script | Shows |
|---|---|
| [data_job.py](examples/scripts/data_job.py) | Ray Data: blocks as the unit of parallelism, `map_batches`, laziness and `materialize()`, and a `groupby` shuffle. |
| [train_job.py](examples/scripts/train_job.py) | Ray Train: one training function per worker, dataset sharding, `ray.train.report`, and retry on node failure. |
| [serve_app.py](examples/scripts/serve_app.py) | Ray Serve: composed deployments, autoscaling replicas, and fractional CPU per replica. |

They reach the pods as a ConfigMap, which keeps every manifest runnable on its own
with no image build and no S3 upload. Real code belongs in an image or in
`runtime_env.working_dir`; a ConfigMap caps out at 1 MiB.

### Two ways to get a cluster

Ray Data, Ray Train, and Ray Serve do not need a `RayCluster` that you created
first. Each KubeRay custom resource can bring its own, and the choice is about the
lifecycle you want rather than about which library you are using:

```bash
# The job brings its own cluster, and it is deleted when the job finishes.
make run-job                          # examples/rayjob-ephemeral.yaml, Ray Data
make job-logs JOB=ray-data-job

# The job runs on a cluster that already exists.
make deploy-example                   # the standing cluster
make run-job-existing                 # examples/rayjob-existing.yaml, Ray Train
make job-logs JOB=ray-train-job

# A long-running service, with a cluster KubeRay manages for it.
make deploy-service                   # examples/rayservice-serve.yaml
make service-status                   # wait for SERVICE STATUS Running
make service-request                  # port-forward and POST a request
make delete-service
```

A cluster per job (`rayClusterSpec`, plus `shutdownAfterJobFinishes: true`) is the
better default: nothing is left running to pay for, and no state leaks into the next
run. The cost is that every submission pays cluster startup, so an interactive loop
of short jobs is better served by a standing cluster and `clusterSelector`, at the
price of jobs contending for the same CPUs.

**Run one example at a time on a small cluster.** Four `ThreadsPerCore: 1` nodes
leave roughly 1.6 CPU each after kubelet reservations and the HyperPod daemonsets,
which is not enough for the standing cluster and a job's own cluster at once. A
`RayJob` whose pods cannot be scheduled waits in `Initializing` indefinitely rather
than failing, then starts as soon as room appears - so `make delete-example` before
`make run-job`.

## Configuration

Override any of these on the `make` command line.

| Make variable | Default | Notes |
|---|---|---|
| `EKS_CLUSTER_NAME` | *(required)* | The EKS cluster orchestrating your HyperPod cluster. |
| `AWS_REGION` | `us-west-2` | Region of the cluster. |
| `KUBERAY_VERSION` | `1.7.1` | Chart version. Ray on HyperPod needs 1.6.0+ for `RayCronJob` and Ray's Kubernetes RBAC auth mode. |
| `KUBERAY_NAMESPACE` | `kuberay-operator` | Created if absent. |
| `KUBERAY_RELEASE` | `kuberay-operator` | Helm release name. |
| `DOMAIN_STACK_NAME` | `hyperpod-ray-domain` | CloudFormation stack name for the domain. |
| `DOMAIN_NAME` | `hyperpod-ray` | SageMaker AI domain name. |
| `USER_PROFILE_NAME` | `ray-user` | User profile to launch Studio as. |
| `DOMAIN_VPC_ID` | *(required for the domain)* | Use the cluster's VPC. |
| `DOMAIN_SUBNET_IDS` | *(required for the domain)* | Prefer the EKS private subnets. |
| `ACCESS_SCOPE_NAMESPACES` | *(empty)* | Empty means whole-cluster access scope. |

Upgrading KubeRay is the same command with a different version:

```bash
make install-kuberay KUBERAY_VERSION=1.7.1
```

## SageMaker Studio access

Optional, and the one part of the setup that genuinely wants CloudFormation: it
spans two consoles, needs cluster ARNs and subnet IDs you have to look up, creates
an execution role, and is repeated per team.

```bash
make deploy-domain EKS_CLUSTER_NAME=my-eks-cluster HYPERPOD_CLUSTER_NAME=my-cluster \
  DOMAIN_VPC_ID=vpc-xxxx DOMAIN_SUBNET_IDS=subnet-a,subnet-b,subnet-c

make domain-access      # the EKS access policies actually granted
make domain-outputs     # the Studio URL to open
```

This automates
[Setting up an Amazon EKS cluster in Studio](https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-studio-setup-eks.html),
which is two grants that are easy to conflate:

| Grant | Why it matters |
|---|---|
| An **IAM policy** on the execution role | Lets the role call AWS APIs. Without `eks:AccessKubernetesApi` the EKS authorizer refuses every call *before* RBAC is consulted, and **`AmazonSageMakerFullAccess` contains no `eks:` actions at all**. Note the two different cluster ARNs: `sagemaker:DescribeCluster` is scoped to the HyperPod cluster, the `eks:` actions to the EKS cluster. |
| **EKS cluster-access policies** | Grant permissions *inside* the cluster. `AmazonSagemakerHyperpodTrainingPolicy` is what makes Ray workloads visible — no custom RBAC needed. |

Their scopes are **not uniform**, which a template applying one scope to all five
would get wrong: `AmazonSagemakerHyperpodUserClusterPolicy` must be cluster-scoped,
and `AmazonSagemakerHyperpodSpaceTemplatePolicy` scoped to `jupyter-k8s-shared`
where the templates live. `ACCESS_SCOPE_NAMESPACES` confines the other three.

When the IAM policy is missing, Studio reports *"The Custom Resource Definition
(CRD) of type … is not configured on the cluster"* — a 403 described as a
configuration problem. The CRD is there; check the IAM policy first.

If you are **creating** a cluster from the official assets, populate
`DataScientistRole1` … `DataScientistRole10` and their namespace parameters. Left
empty, `DataScientistSetupCondition` is false and the whole
`DataScientistSetupStack` is skipped, so none of this is in place. Note that that
stack takes the custom-RBAC route and its role covers
`kubeflow.org/pytorchjobs` but not `ray.io`, so it shows PyTorch tasks and not Ray
ones — use the cluster-access policies for Ray.

The official assets do have a `sagemaker-domain-template.yaml`, but it takes an
`EKSClusterName` parameter and never uses it, so it grants no cluster access, and
the EKS main stack hardcodes `CreateDomain: 'false'`.

## Task governance

Optional. Once a namespace is governed, a `RayCluster` needs Kueue labels in three
places and nothing in the documentation says so:

```bash
# After creating a compute allocation for team <name> from the Policies tab
make deploy-governed TEAM_NAME=<name>
make governed-status      # the RayCluster, the Kueue workload, and warnings together
make governed-quota       # the queues, and how the quota was translated
```

Three things that cost time, all recorded in
[console-install-walkthrough.md](console-install-walkthrough.md):

- **You cannot allocate to an existing namespace.** A compute allocation for team
  `ray` generates namespace `hyperpod-ns-ray` with `hyperpod-ns-ray-localqueue`
  inside it; governed Ray workloads move there. `default` cannot be governed.
- **Labelling only the `RayCluster` fails silently.** Kueue reports the workload
  `Admitted: True` while the cluster sits `suspended`, because the same admission
  policy covers `pods` and KubeRay's generated pods carry no labels. The cause
  appears only in `kubectl get events`. `make governed-status` prints both layers
  for this reason.
- **Quota counts nominal vCPUs.** 4 × `ml.m5.xlarge` becomes a quota of 16 CPU,
  against 7720m the scheduler can actually place on `ThreadsPerCore: 1` nodes — so a
  workload can be admitted and then sit `Pending`.

Gang scheduling is **disabled** by the add-on even though the developer guide says to
confirm it is enabled, and neither the EKS add-on configuration nor the SageMaker
API exposes it.

## Deleting

```bash
make uninstall-kuberay      # the operator
make delete-domain          # the domain, user profile, and access entry
```

**Delete your Ray resources before uninstalling the operator.** Uninstalling it
stops reconciliation of every Ray resource in the cluster: running Ray clusters
keep running but are no longer managed, and deletions never complete. The `ray.io`
CRDs survive an uninstall — Helm never deletes `crds/` contents — so your resource
definitions are not lost.

Delete any spaces and apps in the domain before `make delete-domain`; a domain
with running apps will not delete.

## Documentation

`docs/ray-on-hyperpod.md` is the "Ray on SageMaker HyperPod" chapter of the
SageMaker AI Developer Guide (pages 2784-2849), extracted to Markdown so it is
greppable and cheap for an agent to read. Download the
[SageMaker AI Developer Guide PDF](https://docs.aws.amazon.com/pdfs/sagemaker/latest/dg/sagemaker-dg.pdf)
into `docs/`, then:

```bash
make extract-docs                                   # defaults to pages 2784-2849
make extract-docs DOC_FIRST_PAGE=... DOC_LAST_PAGE=...
```

Both the PDF (roughly 180 MB) and the generated Markdown are gitignored, so run
this once after cloning. Never hand-edit the Markdown. Find the page range for a
chapter from the PDF bookmarks, which the script also uses to assign heading
levels.

Extraction runs out of the repository-level `.venv`, shared with the other
solutions here. `make extract-docs` creates it if missing and installs
[requirements.txt](requirements.txt) into it.

Tables in the extracted Markdown are flattened, because a table cell whose text
wraps becomes several lines. Everything else - headings, fenced code blocks
with language tags, lists, inline code - survives. Check the PDF when a table
matters.

## Scope

Deliberately minimal for now, and aimed at setups that are quick to stand up for
a hands-on session.

**No Route 53.** Ray on HyperPod needs a customer-owned domain with a public
Route 53 hosted zone, an ACM certificate, and a KMS key for exactly two things:
web browser access to a SageMaker AI space, and the HyperPod Ray Endpoint
Operator, which depends on it. Both are out of scope here, because a domain you
own is a much heavier prerequisite than the AWS resources everything else needs.
The consequences: reach the Ray Dashboard with `make dashboard`
(`kubectl port-forward`) rather than an authenticated public URL, and reach a
space from a local IDE over SSH-over-SSM rather than in a browser.

Not yet included, and straightforward to add as separate nested stacks:

- Creating the HyperPod EKS cluster itself (use the official setup assets).
- The SageMaker AI Spaces add-on, for notebook and IDE spaces attached to a Ray
  cluster. Needs version 0.2.0 or later for Ray. Usable without Route 53, as
  long as attendees reach the space from a local IDE over SSH-over-SSM. Watch
  the version matching: the space image's Ray *and* Python versions must equal
  the cluster's, patch version included.
- The HyperPod Observability add-on, for Ray metrics and Grafana dashboards
  (needs version 1.0.6 or later for Ray metrics). No Route 53, but it does need
  an Amazon Managed Grafana workspace, whose IAM Identity Center or SAML setup
  is usually the slow part in a shared account.

Deliberately excluded, rather than merely deferred:

- The HyperPod Ray Endpoint Operator, and web browser access to spaces. See the
  Route 53 note above.
- Task governance compute allocations. Once task governance is on, a namespace
  without an allocation holds a Ray workload unadmitted with no pods at all, and
  preemption deletes a whole Ray cluster including its head. Useful in
  production, but it only adds failure modes to a hands-on session.
- The managed tiered KV cache for Ray Serve, which additionally needs HyperPod
  Tiered Storage enabled on the cluster.

## References

- [Ray on SageMaker HyperPod](https://docs.aws.amazon.com/sagemaker/latest/dg/ray-on-hyperpod.html)
- [aws/sagemaker-hyperpod-cluster-setup](https://github.com/aws/sagemaker-hyperpod-cluster-setup)
- [KubeRay documentation](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
