# HyperPod Mental Model — New Findings (2026-09-09)

Findings from building `hyperpod_ray/` — a CloudFormation solution that installs
the KubeRay operator onto an existing HyperPod EKS cluster. Sources: the
"Ray on SageMaker HyperPod" chapter of the SageMaker AI Developer Guide
(pages 2784–2849, extracted to `hyperpod_ray/docs/ray-on-hyperpod.md`) and
[aws/sagemaker-hyperpod-cluster-setup](https://github.com/aws/sagemaker-hyperpod-cluster-setup)
at `main`.

## Test environment

No live cluster. Doc- and repo-derived, plus read-only `s3api head-object` and
`cloudformation validate-template` calls in account 842413447717
(us-east-1 / us-east-2 / us-west-2).

## New topics (not yet covered)

- **Ray on HyperPod is a first-class HyperPod feature (EKS only).** It is not a
  fork: HyperPod runs upstream, unmodified Ray and KubeRay, and adds
  capabilities *around* them. The entire baseline is two things — a HyperPod
  cluster orchestrated by EKS, plus the KubeRay operator. Everything else
  (Studio Tasks tab, Spaces add-on for attached IDEs, Ray Endpoint Operator for
  authenticated dashboard links, Observability add-on for Ray metrics, task
  governance queueing, tiered checkpointing / hung job detection / node
  recovery, managed tiered KV cache for Ray Serve) is independently adoptable.
  Candidate supplemental doc: `mental-model/hyperpod-ray.md`.

- **KubeRay has no EKS add-on — it is Helm-only.** Unlike observability, task
  governance, the inference operator, and HPTO, there is no `AWS::EKS::Addon`
  for KubeRay. The docs prescribe `helm repo add kuberay
  https://ray-project.github.io/kuberay-helm/` then `helm install`. Any
  CloudFormation automation therefore needs a Helm-capable custom resource. This
  is worth recording because it is easy to assume symmetry with the other
  HyperPod capabilities, all of which *are* add-ons.

- **KubeRay ≥ 1.6.0 is the effective floor on HyperPod.** `RayCronJob` does not
  exist on earlier operators, and Ray's Kubernetes RBAC auth mode
  (`RAY_AUTH_MODE=token`, `RAY_ENABLE_K8S_TOKEN_AUTH=true`) needs KubeRay ≥ 1.6
  with Ray ≥ 2.55.

- **Task governance changes Ray admission semantics.** Once task governance is
  on, a namespace with no compute allocation holds `RayCluster`/`RayJob`
  unadmitted with no pods created at all — it is not a scheduling delay but a
  quota gate, and it is a distinct failure mode from "pods Pending".

## Reference: reusable Helm-in-CloudFormation artifact

The official cluster setup assets publish a Lambda layer containing `helm`,
`kubectl`, `aws-iam-authenticator`, `yq`, and a minimal `git` at:

```
s3://aws-sagemaker-hyperpod-cluster-setup-<region>-prod/resources/artifacts/helm-lambda-layer.zip
```

Verified readable (59 MB) in us-east-1, us-east-2, and us-west-2. Binaries land
at `/opt/python/bin`, shared libs at `/opt/python/lib`. Reusing it removes the
need to build a layer for any Helm-installing custom resource.

Two gotchas that matter when reusing it:

- The layer deliberately **excludes** `libssl`/`libcrypto` so the Lambda
  runtime's own OpenSSL wins; bundling them broke `import ssl` and hung the
  custom resource callback.
- The layer carries no Python packages — not `cfnresponse`, not `PyYAML`. Inline
  custom-resource code must use only stdlib (`urllib.request` for the CFN
  response, and JSON for kubeconfig, which is valid YAML).

The setup assets' own installer authenticates with
`aws-iam-authenticator token -i <cluster>` in the kubeconfig `exec` block, not
`aws eks get-token`, because the AWS CLI is not in the layer.

## Related

Supersedes the self-managed KubeRay approach in `_archived/hyperpod_eks_ray/`,
archived the same day.
