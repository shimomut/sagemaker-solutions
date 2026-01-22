SHELL := /bin/bash

# KubeRay version
KUBERAY_VERSION ?= 1.2.2
NAMESPACE ?= kuberay-system

# Docker/ECR configuration
AWS_REGION ?= us-west-2
AWS_ACCOUNT_ID ?= 842413447717
ECR_REPO_NAME ?= ray-hyperpod
IMAGE_TAG ?= latest
RAY_VERSION ?= 2.42.1

all:

# ===== Docker Image Build =====

# Generate Dockerfile based on blog article
generate-dockerfile:
	@echo "Generating Dockerfile..."
	@echo "# Base Ray image with GPU support" > Dockerfile
	@echo "FROM rayproject/ray:$(RAY_VERSION)-py310-gpu" >> Dockerfile
	@echo "" >> Dockerfile
	@echo "# Install additional dependencies for training" >> Dockerfile
	@echo "RUN pip install --no-cache-dir \\" >> Dockerfile
	@echo "    torch==2.1.0 \\" >> Dockerfile
	@echo "    torchvision==0.16.0 \\" >> Dockerfile
	@echo "    transformers==4.35.0 \\" >> Dockerfile
	@echo "    datasets==2.14.0 \\" >> Dockerfile
	@echo "    accelerate==0.24.0 \\" >> Dockerfile
	@echo "    deepspeed==0.12.0 \\" >> Dockerfile
	@echo "    wandb==0.16.0" >> Dockerfile
	@echo "" >> Dockerfile
	@echo "# Set working directory" >> Dockerfile
	@echo "WORKDIR /app" >> Dockerfile
	@echo "" >> Dockerfile
	@echo "# Copy training scripts (if any)" >> Dockerfile
	@echo "# COPY . /app/" >> Dockerfile
	@echo "" >> Dockerfile
	@echo "# Set environment variables" >> Dockerfile
	@echo "ENV RAY_DEDUP_LOGS=0" >> Dockerfile
	@echo "Dockerfile generated successfully"

# Build Docker image
build:
	docker build --tag $(ECR_REPO_NAME):$(IMAGE_TAG) \
		--build-arg RAY_VERSION=$(RAY_VERSION) .

# Login to ECR
login:
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin \
		$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

# Create ECR repository if it doesn't exist
create-ecr-repo:
	@aws ecr describe-repositories --repository-names $(ECR_REPO_NAME) \
		--region $(AWS_REGION) > /dev/null 2>&1 || \
		aws ecr create-repository --repository-name $(ECR_REPO_NAME) \
		--region $(AWS_REGION)

# Tag image for ECR
tag:
	docker tag $(ECR_REPO_NAME):$(IMAGE_TAG) \
		$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO_NAME):$(IMAGE_TAG)

# Push image to ECR
push:
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO_NAME):$(IMAGE_TAG)

# Build, tag, and push in one command
build-and-push: generate-dockerfile build login create-ecr-repo tag push
	@echo "Image pushed to $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO_NAME):$(IMAGE_TAG)"

# ===== KubeRay Installation =====

# Install KubeRay operator using Helm
install-kuberay:
	helm repo add kuberay https://ray-project.github.io/kuberay-helm/
	helm repo update
	helm install kuberay-operator kuberay/kuberay-operator \
		--namespace $(NAMESPACE) \
		--create-namespace \
		--version $(KUBERAY_VERSION)

# Check KubeRay operator status
status:
	kubectl get pods -n $(NAMESPACE)
	kubectl get crd | grep ray

# List Ray clusters
list-clusters:
	kubectl get rayclusters -A

# List Ray services
list-services:
	kubectl get raysvc -A

# List Ray jobs
list-jobs:
	kubectl get rayjobs -A

# Get all Ray resources
list-all:
	kubectl get rayclusters,raysvc,rayjobs -A

# Watch operator logs
watch-logs:
	kubectl logs -f -n $(NAMESPACE) -l app.kubernetes.io/name=kuberay-operator

# Describe operator deployment
describe:
	kubectl describe deployment kuberay-operator -n $(NAMESPACE)

# Upgrade KubeRay operator
upgrade:
	helm repo update
	helm upgrade kuberay-operator kuberay/kuberay-operator \
		--namespace $(NAMESPACE) \
		--version $(KUBERAY_VERSION)

# Uninstall KubeRay operator
uninstall:
	helm uninstall kuberay-operator -n $(NAMESPACE)

# Clean up namespace (use with caution)
clean-namespace:
	kubectl delete namespace $(NAMESPACE)

# Show Helm values
show-values:
	helm show values kuberay/kuberay-operator --version $(KUBERAY_VERSION)

# Get custom values (if you want to customize installation)
get-values:
	helm get values kuberay-operator -n $(NAMESPACE)

.PHONY: all generate-dockerfile build login create-ecr-repo tag push build-and-push \
	install-kuberay status list-clusters list-services list-jobs list-all \
	watch-logs describe upgrade uninstall clean-namespace show-values get-values
