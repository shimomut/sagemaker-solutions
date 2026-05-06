# Select which image to build/push/deploy. Each image lives under images/<IMAGE>/Dockerfile
# Example: make build IMAGE=nccl-tools
IMAGE ?= shell-tools
IMAGE_DIR = images/$(IMAGE)
ECR_URI = $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/$(IMAGE)

# Target platform for the built image. HyperPod EKS GPU nodes are x86_64,
# so we pin this to linux/amd64 even when building on Apple Silicon (arm64).
# Override with: make build PLATFORM=linux/arm64
PLATFORM ?= linux/amd64

# Optional: restrict the shell pod to a specific EC2 instance type.
# Example: make deploy-shell IMAGE=nccl-tools INSTANCE_TYPE=ml.g5.8xlarge
# Leave unset to let the scheduler pick any eligible node.
INSTANCE_TYPE ?=
ifeq ($(strip $(INSTANCE_TYPE)),)
NODE_SELECTOR :=
else
NODE_SELECTOR := nodeSelector: {node.kubernetes.io/instance-type: $(INSTANCE_TYPE)}
endif

# Optional: request GPUs / EFA devices for the shell pod.
# Defaults to 0 (no request, no device injection by k8s).
# Example: make deploy-shell IMAGE=nccl-tools INSTANCE_TYPE=ml.g5.8xlarge GPU_COUNT=1 EFA_COUNT=1
GPU_COUNT ?= 0
EFA_COUNT ?= 0
ifeq ($(strip $(GPU_COUNT)),0)
GPU_LIMIT :=
else
GPU_LIMIT := nvidia.com/gpu: "$(GPU_COUNT)"
endif
ifeq ($(strip $(EFA_COUNT)),0)
EFA_LIMIT :=
else
EFA_LIMIT := vpc.amazonaws.com/efa: "$(EFA_COUNT)"
endif

# List the images available in this repo
list-images:
	@echo "Available images (set with IMAGE=<name>):"
	@ls -1 images

# Check required environment variables
check-env:
	@echo "Checking required environment variables..."
	@if [ -z "$(REGION)" ]; then \
		echo "Error: REGION environment variable is not set"; \
		echo "Please set it with: export REGION=your-region"; \
		exit 1; \
	fi
	@if [ -z "$(ACCOUNT)" ]; then \
		echo "Error: ACCOUNT environment variable is not set"; \
		echo "Please set it with: export ACCOUNT=your-account-id"; \
		exit 1; \
	fi
	@if [ ! -f "$(IMAGE_DIR)/Dockerfile" ]; then \
		echo "Error: $(IMAGE_DIR)/Dockerfile does not exist"; \
		echo "Available images:"; \
		ls -1 images; \
		exit 1; \
	fi
	@echo "Environment variables are set: REGION=$(REGION), ACCOUNT=$(ACCOUNT), IMAGE=$(IMAGE)"

create-ecr-repo: check-env
	aws ecr create-repository --repository-name $(IMAGE) --region $(REGION) || true

build: check-env
	docker build --platform $(PLATFORM) --tag $(IMAGE) $(IMAGE_DIR)

login: check-env
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com

tag: check-env
	docker tag $(IMAGE):latest $(ECR_URI):latest

push: check-env
	docker push $(ECR_URI):latest

deploy-shell: check-env
	SHELL_IMAGE=$(ECR_URI):latest NODE_SELECTOR='$(NODE_SELECTOR)' \
	GPU_LIMIT='$(GPU_LIMIT)' EFA_LIMIT='$(EFA_LIMIT)' \
	envsubst < shell-pod.yaml | kubectl apply -f -

deploy-shell-default:
	SHELL_IMAGE=ubuntu:22.04 NODE_SELECTOR='$(NODE_SELECTOR)' \
	GPU_LIMIT='$(GPU_LIMIT)' EFA_LIMIT='$(EFA_LIMIT)' \
	envsubst < shell-pod.yaml | kubectl apply -f -

shell:
	kubectl exec -it shell -- bash

delete-shell:
	kubectl delete pod shell

all: create-ecr-repo build login tag push
