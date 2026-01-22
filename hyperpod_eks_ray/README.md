# HyperPod EKS Ray

Setup and utilities for running Ray on AWS SageMaker HyperPod EKS clusters using KubeRay operator.

## Prerequisites

- HyperPod EKS cluster already running
- `kubectl` configured to access your cluster
- `helm` installed (v3+)

## Quick Start

### Install KubeRay Operator

```bash
make install-kuberay
```

This will:
- Add the KubeRay Helm repository
- Install the KubeRay operator in the `kuberay-system` namespace
- Set up Custom Resource Definitions (CRDs) for Ray clusters

### Verify Installation

```bash
make status
```

Expected output should show the KubeRay operator pod running and Ray CRDs installed.

## Usage

### Check Operator Status

```bash
# View operator pods
make status

# Watch operator logs
make watch-logs

# Describe operator deployment
make describe
```

### Manage Ray Clusters

```bash
# List all Ray clusters
make list-clusters

# List Ray services
make list-services

# List Ray jobs
make list-jobs

# List all Ray resources
make list-all
```

### Upgrade KubeRay

```bash
make upgrade
```

### Uninstall

```bash
# Remove KubeRay operator
make uninstall

# Remove namespace (optional, use with caution)
make clean-namespace
```

## Configuration

### Custom Installation

To customize the KubeRay installation, first view available values:

```bash
make show-values
```

Then create a `values.yaml` file and modify the Makefile's `install-kuberay` target to include `-f values.yaml`.

### Change Version or Namespace

```bash
# Install specific version
make install-kuberay KUBERAY_VERSION=1.2.1

# Use different namespace
make install-kuberay NAMESPACE=my-ray-system
```

## Next Steps

After installing KubeRay, you can:

1. Deploy a Ray cluster using `RayCluster` custom resource
2. Submit Ray jobs using `RayJob` custom resource
3. Deploy Ray services using `RayService` custom resource

Example manifests will be added to demonstrate these use cases.

## Resources

- [KubeRay Documentation](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
- [Ray Documentation](https://docs.ray.io/)
- [KubeRay GitHub](https://github.com/ray-project/kuberay)
