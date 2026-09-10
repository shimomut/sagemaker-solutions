# Ray on HyperPod - CloudFormation setup

Automates the setup of a **Ray on SageMaker HyperPod** environment with
CloudFormation.

Ray on HyperPod is an official HyperPod feature. It runs the upstream, unmodified
open source Ray and KubeRay, and HyperPod adds capabilities around them
(Studio integration, authenticated dashboard access, task governance queueing,
resilient training, observability). Per the developer guide, the whole baseline
is two things:

1. A HyperPod cluster orchestrated by Amazon EKS.
2. The KubeRay operator installed on it.

This solution automates step 2. Step 1 stays with
[aws/sagemaker-hyperpod-cluster-setup](https://github.com/aws/sagemaker-hyperpod-cluster-setup),
the official cluster setup assets, for now. Keeping them separate makes the
iteration loop fast: you create the cluster once and redeploy just the Ray part
as it grows.

## Contents

| Path | What it is |
|---|---|
| [cfn/kuberay-operator.yaml](cfn/kuberay-operator.yaml) | The stack. Installs the KubeRay operator onto an existing HyperPod EKS cluster. |
| [examples/ray-cluster.yaml](examples/ray-cluster.yaml) | A minimal `RayCluster` for verifying the setup. |
| [scripts/extract_pdf_docs.py](scripts/extract_pdf_docs.py) | Extracts a page range of an AWS docs PDF to Markdown. |
| `docs/ray-on-hyperpod.md` | The "Ray on SageMaker HyperPod" chapter, extracted for easy reading by humans and agents. Generated locally, not committed. |
| [Makefile](Makefile) | Deploy, inspect, verify, and tear down. |

## Prerequisites

- A running HyperPod cluster orchestrated by Amazon EKS. The EKS cluster's
  authentication mode must include `API` (`API` or `API_AND_CONFIG_MAP`), which
  is what the official setup assets configure.
- AWS CLI, configured with permissions to create IAM roles, Lambda functions,
  and EKS access entries.
- `kubectl` for the verification steps.

## Quick start

```bash
# Create or update the stack
make deploy EKS_CLUSTER_NAME=my-hyperpod-eks-cluster

# Verify the operator is running
make kubeconfig EKS_CLUSTER_NAME=my-hyperpod-eks-cluster
make operator-status
make crds
```

`make help` lists every target.

Then verify end to end with a real Ray cluster:

```bash
make deploy-example
make list-clusters
make dashboard        # http://localhost:8265
make delete-example
```

## Configuration

Override any of these on the `make` command line, or pass the matching template
parameter directly.

| Make variable | Template parameter | Default | Notes |
|---|---|---|---|
| `EKS_CLUSTER_NAME` | `EKSClusterName` | *(required)* | The EKS cluster orchestrating your HyperPod cluster. |
| `AWS_REGION` | - | `us-west-2` | Region of the cluster and the stack. |
| `STACK_NAME` | - | `hyperpod-ray` | CloudFormation stack name. |
| `RESOURCE_PREFIX` | `ResourceNamePrefix` | `hyperpod-ray` | Prefix for created resource names. |
| `KUBERAY_VERSION` | `KubeRayVersion` | `1.7.0` | Chart version. Ray on HyperPod needs 1.6.0+ for `RayCronJob` and Ray's Kubernetes RBAC auth mode. |
| `KUBERAY_NAMESPACE` | `KubeRayNamespace` | `kuberay-operator` | Created if absent. |
| `KUBERAY_RELEASE` | `KubeRayReleaseName` | `kuberay-operator` | Helm release name. |
| `INSTALLER_SUBNET_IDS` | `InstallerSubnetIds` | *(empty)* | Only for private EKS API endpoints. See below. |
| `INSTALLER_SECURITY_GROUP_IDS` | `InstallerSecurityGroupIds` | *(empty)* | Paired with the above. |

Upgrading KubeRay is a stack update:

```bash
make deploy EKS_CLUSTER_NAME=my-cluster KUBERAY_VERSION=1.7.0
```

## How the stack works

CloudFormation cannot run Helm, so the stack wraps `helm upgrade --install` in a
Lambda-backed custom resource. This mirrors the pattern the official cluster
setup assets use for the HyperPod Helm chart:

1. An IAM role for the installer function, plus an `AWS::EKS::AccessEntry` that
   grants it `AmazonEKSClusterAdminPolicy`. Cluster-admin is genuinely needed:
   the chart installs CRDs and cluster-scoped RBAC.
2. A Lambda layer carrying the `helm`, `kubectl`, and `aws-iam-authenticator`
   binaries. Rather than build one, the stack reuses the layer artifact that the
   HyperPod cluster setup assets publish at
   `s3://aws-sagemaker-hyperpod-cluster-setup-<region>-prod/resources/artifacts/helm-lambda-layer.zip`.
   Override `HelmToolsLayerS3Bucket` and `HelmToolsLayerS3Key` to supply your own.
3. The installer function, whose code is inline in the template. It builds a
   kubeconfig from `eks:DescribeCluster`, then runs `helm upgrade --install` on
   create and update, and `helm uninstall` on delete.

Because the function reports a physical resource ID of `<namespace>/<release>`,
renaming either one replaces the release instead of orphaning it.

### Private API endpoints

The installer runs outside your VPC by default, which works because HyperPod EKS
clusters created by the official assets expose a public API endpoint. If yours is
private-only, set `INSTALLER_SUBNET_IDS` and `INSTALLER_SECURITY_GROUP_IDS`. The
subnets need NAT egress so the installer can still reach the Helm repository, and
the cluster security group must allow the installer's security groups inbound on
443.

## Troubleshooting

The Helm output goes to CloudWatch:

```bash
make logs
make events      # if the stack itself is stuck or rolled back
```

Common failures:

- **`ResourceInUseException` on the access entry** - an access entry already
  exists for this principal. That should not happen with a freshly created role;
  it does if you deleted the stack while retaining the role.
- **The custom resource times out** - almost always the installer failing to
  reach either the EKS API endpoint or `ray-project.github.io`. Check the log
  group, then the private-endpoint note above.
- **`helm upgrade` reports the release is in a pending state** - a previous
  attempt was interrupted. Roll it back or delete the release with `helm` before
  redeploying.

## Deleting

```bash
make delete
```

**Delete your Ray resources before you delete the stack.** Uninstalling the
operator stops reconciliation of every Ray resource in the cluster: running Ray
clusters keep running but are no longer managed, and deletions never complete.

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

Deliberately minimal for now. Not yet included, and straightforward to add as
separate nested stacks:

- Creating the HyperPod EKS cluster itself (use the official setup assets).
- The SageMaker AI Spaces add-on, for notebook and IDE spaces attached to a Ray
  cluster.
- The HyperPod Ray Endpoint Operator, for authenticated Ray Dashboard links and
  remote job submission.
- The HyperPod Observability add-on, for Ray metrics and Grafana dashboards
  (needs version 1.0.6 or later for Ray metrics).
- Task governance compute allocations, which Ray workloads need in order to be
  admitted once task governance is on.

## References

- [Ray on SageMaker HyperPod](https://docs.aws.amazon.com/sagemaker/latest/dg/ray-on-hyperpod.html)
- [aws/sagemaker-hyperpod-cluster-setup](https://github.com/aws/sagemaker-hyperpod-cluster-setup)
- [KubeRay documentation](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
