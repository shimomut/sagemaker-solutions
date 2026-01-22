# HyperPod EKS Ray

Setup and utilities for running Ray on AWS SageMaker HyperPod EKS clusters using KubeRay operator.

## Prerequisites

- HyperPod EKS cluster already running
- `kubectl` configured to access your cluster
- `helm` installed (v3+)
- Docker installed (for building custom Ray images)
- AWS CLI configured with appropriate permissions

## Quick Start

### 1. Build and Push Custom Ray Image

Based on the [AWS blog article](https://aws.amazon.com/blogs/machine-learning/ray-jobs-on-amazon-sagemaker-hyperpod-scalable-and-resilient-distributed-ai/), create a custom Ray container image with your training dependencies:

```bash
# Generate Dockerfile, build, and push to ECR in one command
make build-and-push
```

Or run steps individually:

```bash
# Generate Dockerfile from template
make generate-dockerfile

# Build Docker image
make build

# Login to ECR
make login

# Create ECR repository (if needed)
make create-ecr-repo

# Tag image for ECR
make tag

# Push to ECR
make push
```

The default configuration uses:
- Base image: `rayproject/ray:2.42.1-py310-gpu`
- Includes: PyTorch, Transformers, DeepSpeed, Accelerate, and other ML libraries

To customize:

```bash
# Use different Ray version
make build-and-push RAY_VERSION=2.40.0

# Use different ECR repository name
make build-and-push ECR_REPO_NAME=my-ray-image

# Use different AWS region
make build-and-push AWS_REGION=us-west-2
```

### 2. Install KubeRay Operator

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

## Docker Image Configuration

### Customizing the Dockerfile

After running `make generate-dockerfile`, you can edit the generated `Dockerfile` to add your own dependencies:

```dockerfile
# Add custom Python packages
RUN pip install --no-cache-dir \
    your-package==1.0.0 \
    another-package==2.0.0

# Copy your training code
COPY ./training /app/training
```

Then rebuild and push:

```bash
make build login tag push
```

### Environment Variables

You can customize the build using these variables:

- `AWS_REGION`: AWS region for ECR (default: `us-east-1`)
- `AWS_ACCOUNT_ID`: AWS account ID (default: `842413447717`)
- `ECR_REPO_NAME`: ECR repository name (default: `ray-hyperpod`)
- `IMAGE_TAG`: Docker image tag (default: `latest`)
- `RAY_VERSION`: Ray version to use (default: `2.42.1`)

## KubeRay Configuration

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

After installing KubeRay and building your custom image, you can:

1. Create an FSx for Lustre file system for shared storage (required for multi-node clusters)
2. Deploy a Ray cluster using `RayCluster` custom resource with your custom image
3. Submit Ray jobs using the Ray Jobs SDK or by exec'ing into the head pod
4. Implement checkpointing for fault tolerance and auto-resume capabilities

### Example Ray Cluster Manifest

Use your custom ECR image in the Ray cluster manifest:

```yaml
apiVersion: ray.io/v1
kind: RayCluster
metadata:
  name: ray-cluster
spec:
  rayVersion: '2.42.1'
  headGroupSpec:
    rayStartParams:
      dashboard-host: '0.0.0.0'
    template:
      spec:
        containers:
        - name: ray-head
          image: 842413447717.dkr.ecr.us-east-1.amazonaws.com/ray-hyperpod:latest
          resources:
            limits:
              cpu: "2"
              memory: "8Gi"
  workerGroupSpecs:
  - replicas: 2
    minReplicas: 1
    maxReplicas: 4
    groupName: gpu-workers
    rayStartParams: {}
    template:
      spec:
        containers:
        - name: ray-worker
          image: 842413447717.dkr.ecr.us-east-1.amazonaws.com/ray-hyperpod:latest
          resources:
            limits:
              nvidia.com/gpu: "8"
              cpu: "96"
              memory: "1000Gi"
```

## Resources

- [KubeRay Documentation](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
- [Ray Documentation](https://docs.ray.io/)
- [KubeRay GitHub](https://github.com/ray-project/kuberay)
