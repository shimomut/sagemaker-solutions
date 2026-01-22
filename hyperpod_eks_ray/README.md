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

**Note:** The image is built for `linux/amd64` platform to ensure compatibility with HyperPod x86_64 instances, even when building on Apple Silicon (ARM) machines.

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

### 3. Generate and Deploy Ray Cluster

Generate a Ray cluster manifest with your custom image:

```bash
# Generate ray-cluster.yaml with default settings
make generate-ray-cluster

# Deploy the Ray cluster
make deploy-ray-cluster
```

Customize the cluster configuration:

```bash
# Use different instance types and sizes
make generate-ray-cluster \
  CLUSTER_NAME=my-ray-cluster \
  HEAD_INSTANCE_TYPE=ml.m5.4xlarge \
  WORKER_INSTANCE_TYPE=ml.p4d.24xlarge \
  WORKER_REPLICAS=4 \
  WORKER_GPU=8

# Then deploy
make deploy-ray-cluster
```

Available configuration variables:
- `CLUSTER_NAME`: Name of the Ray cluster (default: `ray-cluster`)
- `HEAD_CPU`: CPU for head node (default: `2`)
- `HEAD_MEMORY`: Memory for head node (default: `8Gi`)
- `HEAD_INSTANCE_TYPE`: Instance type for head node (default: `ml.m5.2xlarge`)
- `WORKER_REPLICAS`: Initial number of workers (default: `2`)
- `WORKER_MIN_REPLICAS`: Minimum workers for autoscaling (default: `1`)
- `WORKER_MAX_REPLICAS`: Maximum workers for autoscaling (default: `4`)
- `WORKER_GPU`: GPUs per worker (default: `8`)
- `WORKER_CPU`: CPUs per worker (default: `96`)
- `WORKER_MEMORY`: Memory per worker (default: `1000Gi`)
- `WORKER_INSTANCE_TYPE`: Instance type for workers (default: `ml.p5.48xlarge`)
- `FSX_PVC_NAME`: FSx PVC name for shared storage (default: `fsx-claim`)

### 4. Verify Installation

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

# Delete Ray cluster
make delete-ray-cluster

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

After deploying your Ray cluster, you can:

1. **Access the Ray Dashboard**: Port-forward to view the dashboard
   ```bash
   kubectl port-forward -n default service/ray-cluster-head-svc 8265:8265
   ```
   Then visit http://localhost:8265

2. **Submit Ray Jobs**: Use the Ray Jobs SDK
   ```bash
   ray job submit --address http://localhost:8265 \
     --working-dir ./my-training-code \
     -- python train.py
   ```

3. **Exec into Head Pod**: Run jobs directly
   ```bash
   kubectl exec -it $(kubectl get pods -l ray-node-type=head -o name) -- bash
   python my_script.py
   ```

4. **Implement Checkpointing**: For fault tolerance and auto-resume
   - Save checkpoints to `/fsx` (FSx shared storage)
   - Use Ray Train's checkpoint API
   - Set `max_failures=-1` in FailureConfig for unlimited retries

### Example Ray Training Script

See the [AWS blog article](https://aws.amazon.com/blogs/machine-learning/ray-jobs-on-amazon-sagemaker-hyperpod-scalable-and-resilient-distributed-ai/) for complete examples of:
- Distributed training with Ray Train
- Checkpointing for fault tolerance
- Auto-resume on worker failures

## Resources

- [KubeRay Documentation](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
- [Ray Documentation](https://docs.ray.io/)
- [KubeRay GitHub](https://github.com/ray-project/kuberay)
