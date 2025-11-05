# Kubernetes Shell Pod

This directory contains a YAML configuration and Dockerfile for an interactive shell pod to help with debugging and development.

## Quick Start with Make Commands

Set your AWS account and region, then use the Makefile for easy management:

```bash
# Set environment variables (REQUIRED)
export ACCOUNT=123456789012
export REGION=us-west-2

# Build and push custom image to ECR
make all

# Deploy shell pod with custom image
make deploy-shell

# Connect to the shell
make shell

# Clean up when done
make delete-shell
```

**Note:** The Makefile will automatically check that `REGION` and `ACCOUNT` environment variables are set before executing commands that require them. If they're not set, the command will fail with a helpful error message.

## Manual Usage

### Building the Shell Image

Build a custom image with additional tools (Python, AWS CLI, kubectl):

```bash
# Build the image
docker build -t shell-tools:latest tools/k8s-shell/

# Tag and push to your registry (optional)
docker tag shell-tools:latest your-registry/shell-tools:latest
docker push your-registry/shell-tools:latest
```

### Shell Pod Deployment

**Usage with default Ubuntu image:**
```bash
# Deploy the pod
make deploy-shell-default

# Or manually:
kubectl apply -f tools/k8s-shell/shell-pod.yaml
```

**Usage with custom shell image:**
```bash
# Deploy with custom ECR image
make deploy-shell

# Or manually:
export SHELL_IMAGE=your-registry/shell-tools:latest
envsubst < tools/k8s-shell/shell-pod.yaml | kubectl apply -f -
```

**Connect and clean up:**
```bash
# Connect to the shell
make shell
# Or: kubectl exec -it shell -- bash

# Clean up
make delete-shell
# Or: kubectl delete pod shell
```

## Available Make Targets

- `make check-env` - Verify REGION and ACCOUNT environment variables are set
- `make create-ecr-repo` - Create ECR repository (requires env vars)
- `make build` - Build Docker image locally
- `make login` - Login to ECR (requires env vars)
- `make tag` - Tag image for ECR (requires env vars)
- `make push` - Push image to ECR (requires env vars)
- `make all` - Complete build and push workflow (requires env vars)
- `make deploy-shell` - Deploy pod with custom ECR image (requires env vars)
- `make deploy-shell-default` - Deploy pod with default Ubuntu image
- `make shell` - Connect to running pod
- `make delete-shell` - Remove the pod

**Environment Variable Requirements:**
Commands marked with "requires env vars" will automatically check for `REGION` and `ACCOUNT` environment variables and fail with helpful error messages if they're not set.

## Common Use Cases

### AWS Operations
```bash
# Inside the pod (with custom image)
aws s3 ls
aws sts get-caller-identity
```

### Python Development
```bash
# Inside the pod (with custom image)
python --version
pip list
jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser --allow-root
```

### Kubernetes Operations
```bash
# Inside the pod (with custom image)
kubectl get pods
kubectl get nodes
```

### Network Testing
```bash
# Inside the pod
curl -I https://huggingface.co
nslookup kubernetes.default.svc.cluster.local
```

### File System Testing
```bash
# Inside the pod
ls -la /workspace
ls -la /fsx  # FSx Lustre mount
df -h
```

## Included Tools (Custom Image)

The custom Dockerfile includes:
- Python 3.11 with pip
- AWS CLI v2
- kubectl
- Common development tools (git, vim, curl, wget, jq, htop, tree)
- Python packages: boto3, requests, pyyaml, numpy, pandas, matplotlib, jupyter, ipython

## Notes

- The pod uses `sleep infinity` to stay running for interactive access
- Default Ubuntu 22.04 image or custom image with development tools
- Includes workspace volume and FSx Lustre mount at `/fsx`
- Memory allocation: 1-2GB with CPU limits
- Remember to clean up the pod when done to free cluster resources