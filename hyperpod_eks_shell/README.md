# Kubernetes Shell Pod

This directory contains a YAML configuration and a set of Dockerfiles for interactive pods used for debugging, development, and benchmarking on HyperPod EKS clusters.

## Available Images

Each image lives in its own subdirectory under `images/`. You pick which one to build and deploy with the `IMAGE` variable.

| IMAGE name    | Path                             | Purpose |
|---------------|----------------------------------|---------|
| `shell-tools` | `images/shell-tools/Dockerfile`  | General-purpose Ubuntu 22.04 shell with Python 3.11, AWS CLI v2, boto3, and common dev tools. Default. |
| `nccl-tools`  | `images/nccl-tools/Dockerfile`   | CUDA + EFA + NCCL + nccl-tests binaries for multi-node GPU collective-comm benchmarks. Based on the upstream [awsome-distributed-training nccl-tests.Dockerfile](https://github.com/awslabs/awsome-distributed-training/blob/main/micro-benchmarks/nccl-tests/nccl-tests.Dockerfile). Named `nccl-tools` to avoid clashing with the real `nccl-tests` image. |

List them at any time with:
```bash
make list-images
```

To add a new image, drop a `Dockerfile` into `images/<your-image-name>/` and reference it with `IMAGE=<your-image-name>`.

## Quick Start with Make Commands

Set your AWS account and region, pick an image, then use the Makefile:

```bash
# Required environment
export ACCOUNT=123456789012
export REGION=us-west-2

# Build and push the default shell-tools image
make all

# ...or build and push the nccl-tools image
make all IMAGE=nccl-tools

# Deploy a shell pod using the last-built image
make deploy-shell IMAGE=nccl-tools

# Optional: pin the pod to a specific EC2 instance type
make deploy-shell IMAGE=nccl-tools INSTANCE_TYPE=ml.g5.8xlarge

# Connect to the shell
make shell

# Clean up
make delete-shell
```

`IMAGE` defaults to `shell-tools`. All image-aware targets (`build`, `tag`, `push`, `create-ecr-repo`, `deploy-shell`, `all`) honor it.

### Targeting a specific instance type

The deploy targets accept an `INSTANCE_TYPE` variable. When set, the pod spec gets a `nodeSelector` of `node.kubernetes.io/instance-type: <value>`. When unset, the scheduler picks any eligible node.

```bash
# List what's available on your cluster
kubectl get nodes -L node.kubernetes.io/instance-type

# Pin the nccl-tools pod to a GPU node
make deploy-shell IMAGE=nccl-tools INSTANCE_TYPE=ml.g5.8xlarge

# Pin the default shell to a CPU node
make deploy-shell-default INSTANCE_TYPE=ml.m5.xlarge
```

### Requesting GPUs and EFA devices

`GPU_COUNT` and `EFA_COUNT` control the `resources.limits` entries on the container. Both default to `0` (no request, no device plugin reservation).

```bash
# GPU-only shell
make deploy-shell IMAGE=nccl-tools INSTANCE_TYPE=ml.g5.8xlarge GPU_COUNT=1

# GPU + EFA for multi-node NCCL work
make deploy-shell IMAGE=nccl-tools INSTANCE_TYPE=ml.p5.48xlarge GPU_COUNT=8 EFA_COUNT=32
```

Setting `GPU_COUNT>0` adds `nvidia.com/gpu: "<n>"` so the NVIDIA device plugin reserves the GPU(s) for your pod (with proper scheduler isolation). Setting `EFA_COUNT>0` adds `vpc.amazonaws.com/efa: "<n>"` so the AWS EFA device plugin maps `/dev/infiniband/*` and the EFA userspace into the container.

Notes:
- NVIDIA CUDA base images set `NVIDIA_VISIBLE_DEVICES=all`, so a pod on a GPU node sees GPUs even without `GPU_COUNT` — but without the request, the scheduler won't reserve them and another pod can co-schedule on top of yours. Always set `GPU_COUNT` when you actually need the device.
- EFA has no equivalent auto-inject. Without `EFA_COUNT`, `/dev/infiniband` is absent and `fi_info -p efa` returns no providers.
- You still pass `INSTANCE_TYPE` if you want to pin to a specific node family.

### Target architecture (Apple Silicon users)

The Makefile always builds for `linux/amd64` via `docker build --platform linux/amd64`, because HyperPod EKS GPU nodes are x86_64. This matters on Apple Silicon Macs (arm64), where a default `docker build` would produce an arm64 image that can't run on the cluster. Docker Desktop uses QEMU for the cross-build, so expect builds to be slower than a native build.

Override the platform if you ever need a different arch:
```bash
make build IMAGE=shell-tools PLATFORM=linux/arm64
```

**Note:** The Makefile checks that `REGION` and `ACCOUNT` are set and that `images/$(IMAGE)/Dockerfile` exists. If any check fails you'll get a helpful error.

## Manual Usage

### Building an image

On Apple Silicon you want `--platform=linux/amd64` so the image runs on x86_64 HyperPod EKS nodes:

```bash
# Default shell-tools
docker build --platform=linux/amd64 -t shell-tools:latest images/shell-tools/

# nccl-tools
docker build --platform=linux/amd64 -t nccl-tools:latest images/nccl-tools/
```

`make build` already passes `--platform=linux/amd64` by default.

### Pushing to ECR

```bash
export ACCOUNT=123456789012
export REGION=us-west-2

make create-ecr-repo IMAGE=nccl-tools
make login
make tag  IMAGE=nccl-tools
make push IMAGE=nccl-tools
```

### Shell Pod Deployment

With default Ubuntu image (no custom build needed):
```bash
make deploy-shell-default
# Or manually:
# kubectl apply -f shell-pod.yaml
```

With a custom ECR image:
```bash
make deploy-shell IMAGE=shell-tools
# or
make deploy-shell IMAGE=nccl-tools

# Or manually:
export SHELL_IMAGE=${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/nccl-tools:latest
envsubst < shell-pod.yaml | kubectl apply -f -
```

Connect and clean up:
```bash
make shell          # or: kubectl exec -it shell -- bash
make delete-shell   # or: kubectl delete pod shell
```

## Available Make Targets

- `make list-images` - Show the images available under `images/`
- `make check-env` - Verify `REGION`, `ACCOUNT`, and the selected Dockerfile exist
- `make create-ecr-repo` - Create ECR repository for `$(IMAGE)` (requires env vars)
- `make build` - Build `$(IMAGE)` locally from `images/$(IMAGE)/Dockerfile`
- `make login` - Login to ECR (requires env vars)
- `make tag` - Tag `$(IMAGE):latest` for ECR (requires env vars)
- `make push` - Push `$(IMAGE):latest` to ECR (requires env vars)
- `make all` - `create-ecr-repo` + `build` + `login` + `tag` + `push` for `$(IMAGE)`
- `make deploy-shell` - Deploy pod using the ECR URI for `$(IMAGE)` (requires env vars)
- `make deploy-shell-default` - Deploy pod with `ubuntu:22.04`
- `make shell` - Exec into the running pod
- `make delete-shell` - Remove the pod

## Notes on the `nccl-tools` image

The pod template in `shell-pod.yaml` does not request GPUs or EFA devices by default. If you want to actually run NCCL benchmarks across nodes, you'll want to:

- Add `resources.limits."nvidia.com/gpu"` and EFA device requests to the pod spec, or use a dedicated multi-node manifest.
- Schedule onto HyperPod EKS GPU worker nodes (e.g., `p5`, `p4d`).

For an interactive single-pod sanity check you can still deploy it as-is and use the compiled binaries under `/opt/nccl-tests/build/`.

### Local patch vs. the upstream Dockerfile

The EFA installer step is the one divergence from the upstream awsome-distributed-training `nccl-tests.Dockerfile`. EFA 1.48's installer in dpkg mode (`-d`) installs its bundled `.deb` packages one at a time, and after the Dockerfile's earlier `apt-get remove` of rdma-core, `libfabric1-aws` gets installed before `ibverbs-providers (>= 59)` is in place and the build fails with:

```
dpkg: dependency problems prevent configuration of libfabric1-aws:
 libfabric1-aws depends on ibverbs-providers (>= 59); however:
  Package ibverbs-providers is not installed.
```

Our Dockerfile pre-installs the bundled debs in a single `dpkg -i DEBS/UBUNTU2204/<arch>/*.deb` call (one invocation lets dpkg resolve all inter-deb dependencies at once), then runs `efa_installer.sh`. Already-installed packages are a no-op for the installer. This is a local workaround, not an upstream bug fix.

## Common Use Cases

### AWS Operations
```bash
aws s3 ls
aws sts get-caller-identity
```

### Python Development (shell-tools)
```bash
python --version
pip list
```

### Kubernetes Operations
```bash
kubectl get pods
kubectl get nodes
```

### Network Testing
```bash
curl -I https://huggingface.co
nslookup kubernetes.default.svc.cluster.local
```

### File System Testing
```bash
ls -la /workspace
ls -la /fsx  # FSx Lustre mount
df -h
```

### NCCL sanity (nccl-tools)
```bash
# Inside the pod
/opt/nccl-tests/build/all_reduce_perf -b 8 -e 128M -f 2 -g 1
```

## Included Tools

### `shell-tools` image
- Python 3.11 with pip
- AWS CLI v2
- boto3, requests, ipython
- Common dev tools: git, vim, curl, wget, jq, htop, tree, unzip

### `nccl-tools` image
- CUDA 13.0 devel on Ubuntu 22.04
- AWS EFA installer 1.48.0 with bundled OFI NCCL plugin
- NVIDIA GDRCopy
- NCCL (built from source)
- nccl-tests (built from source, available at `/opt/nccl-tests/build/`)
- OpenMPI (from the EFA installer)

## General Notes

- The pod uses `sleep infinity` to stay running for interactive access.
- Volumes mounted: `/workspace` (emptyDir), `/host-root` (host root), `/fsx` (FSx Lustre PVC named `fsx-claim`).
- Memory allocation: 1-2Gi with CPU limits in the default manifest.
- Remember to delete the pod when you're done to free cluster resources.
