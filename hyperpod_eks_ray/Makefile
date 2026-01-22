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

# Ray cluster configuration
CLUSTER_NAME ?= ray-cluster
HEAD_CPU ?= 2
HEAD_MEMORY ?= 8Gi
HEAD_INSTANCE_TYPE ?= ml.m5.2xlarge
WORKER_REPLICAS ?= 2
WORKER_MIN_REPLICAS ?= 1
WORKER_MAX_REPLICAS ?= 4
WORKER_GPU ?= 8
WORKER_CPU ?= 96
WORKER_MEMORY ?= 1000Gi
WORKER_INSTANCE_TYPE ?= ml.p5.48xlarge
FSX_PVC_NAME ?= fsx-claim

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

# Build Docker image (for x86_64/amd64 platform)
build:
	docker build --platform linux/amd64 \
		--tag $(ECR_REPO_NAME):$(IMAGE_TAG) \
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

# ===== Ray Cluster Manifest =====

# Generate Ray cluster manifest
generate-ray-cluster:
	@echo "Generating Ray cluster manifest..."
	@echo "apiVersion: ray.io/v1" > ray-cluster.yaml
	@echo "kind: RayCluster" >> ray-cluster.yaml
	@echo "metadata:" >> ray-cluster.yaml
	@echo "  name: $(CLUSTER_NAME)" >> ray-cluster.yaml
	@echo "spec:" >> ray-cluster.yaml
	@echo "  rayVersion: '$(RAY_VERSION)'" >> ray-cluster.yaml
	@echo "  headGroupSpec:" >> ray-cluster.yaml
	@echo "    rayStartParams:" >> ray-cluster.yaml
	@echo "      dashboard-host: '0.0.0.0'" >> ray-cluster.yaml
	@echo "      block: 'true'" >> ray-cluster.yaml
	@echo "    template:" >> ray-cluster.yaml
	@echo "      metadata:" >> ray-cluster.yaml
	@echo "        labels:" >> ray-cluster.yaml
	@echo "          app: ray" >> ray-cluster.yaml
	@echo "          ray-node-type: head" >> ray-cluster.yaml
	@echo "      spec:" >> ray-cluster.yaml
	@echo "        nodeSelector:" >> ray-cluster.yaml
	@echo "          node.kubernetes.io/instance-type: $(HEAD_INSTANCE_TYPE)" >> ray-cluster.yaml
	@echo "        containers:" >> ray-cluster.yaml
	@echo "        - name: ray-head" >> ray-cluster.yaml
	@echo "          image: $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO_NAME):$(IMAGE_TAG)" >> ray-cluster.yaml
	@echo "          ports:" >> ray-cluster.yaml
	@echo "          - containerPort: 6379" >> ray-cluster.yaml
	@echo "            name: gcs" >> ray-cluster.yaml
	@echo "          - containerPort: 8265" >> ray-cluster.yaml
	@echo "            name: dashboard" >> ray-cluster.yaml
	@echo "          - containerPort: 10001" >> ray-cluster.yaml
	@echo "            name: client" >> ray-cluster.yaml
	@echo "          resources:" >> ray-cluster.yaml
	@echo "            limits:" >> ray-cluster.yaml
	@echo "              cpu: \"$(HEAD_CPU)\"" >> ray-cluster.yaml
	@echo "              memory: \"$(HEAD_MEMORY)\"" >> ray-cluster.yaml
	@echo "            requests:" >> ray-cluster.yaml
	@echo "              cpu: \"$(HEAD_CPU)\"" >> ray-cluster.yaml
	@echo "              memory: \"$(HEAD_MEMORY)\"" >> ray-cluster.yaml
	@echo "          volumeMounts:" >> ray-cluster.yaml
	@echo "          - name: fsx-storage" >> ray-cluster.yaml
	@echo "            mountPath: /fsx" >> ray-cluster.yaml
	@echo "        volumes:" >> ray-cluster.yaml
	@echo "        - name: fsx-storage" >> ray-cluster.yaml
	@echo "          persistentVolumeClaim:" >> ray-cluster.yaml
	@echo "            claimName: $(FSX_PVC_NAME)" >> ray-cluster.yaml
	@echo "  workerGroupSpecs:" >> ray-cluster.yaml
	@echo "  - replicas: $(WORKER_REPLICAS)" >> ray-cluster.yaml
	@echo "    minReplicas: $(WORKER_MIN_REPLICAS)" >> ray-cluster.yaml
	@echo "    maxReplicas: $(WORKER_MAX_REPLICAS)" >> ray-cluster.yaml
	@echo "    groupName: gpu-workers" >> ray-cluster.yaml
	@echo "    rayStartParams:" >> ray-cluster.yaml
	@echo "      block: 'true'" >> ray-cluster.yaml
	@echo "    template:" >> ray-cluster.yaml
	@echo "      metadata:" >> ray-cluster.yaml
	@echo "        labels:" >> ray-cluster.yaml
	@echo "          app: ray" >> ray-cluster.yaml
	@echo "          ray-node-type: worker" >> ray-cluster.yaml
	@echo "      spec:" >> ray-cluster.yaml
	@echo "        nodeSelector:" >> ray-cluster.yaml
	@echo "          node.kubernetes.io/instance-type: $(WORKER_INSTANCE_TYPE)" >> ray-cluster.yaml
	@echo "        containers:" >> ray-cluster.yaml
	@echo "        - name: ray-worker" >> ray-cluster.yaml
	@echo "          image: $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO_NAME):$(IMAGE_TAG)" >> ray-cluster.yaml
	@echo "          resources:" >> ray-cluster.yaml
	@echo "            limits:" >> ray-cluster.yaml
	@echo "              nvidia.com/gpu: \"$(WORKER_GPU)\"" >> ray-cluster.yaml
	@echo "              vpc.amazonaws.com/efa: \"1\"" >> ray-cluster.yaml
	@echo "              cpu: \"$(WORKER_CPU)\"" >> ray-cluster.yaml
	@echo "              memory: \"$(WORKER_MEMORY)\"" >> ray-cluster.yaml
	@echo "            requests:" >> ray-cluster.yaml
	@echo "              nvidia.com/gpu: \"$(WORKER_GPU)\"" >> ray-cluster.yaml
	@echo "              vpc.amazonaws.com/efa: \"1\"" >> ray-cluster.yaml
	@echo "              cpu: \"$(WORKER_CPU)\"" >> ray-cluster.yaml
	@echo "              memory: \"$(WORKER_MEMORY)\"" >> ray-cluster.yaml
	@echo "          volumeMounts:" >> ray-cluster.yaml
	@echo "          - name: fsx-storage" >> ray-cluster.yaml
	@echo "            mountPath: /fsx" >> ray-cluster.yaml
	@echo "        volumes:" >> ray-cluster.yaml
	@echo "        - name: fsx-storage" >> ray-cluster.yaml
	@echo "          persistentVolumeClaim:" >> ray-cluster.yaml
	@echo "            claimName: $(FSX_PVC_NAME)" >> ray-cluster.yaml
	@echo "Ray cluster manifest generated: ray-cluster.yaml"

# Deploy Ray cluster
deploy-ray-cluster:
	kubectl apply -f ray-cluster.yaml

# Delete Ray cluster
delete-ray-cluster:
	kubectl delete -f ray-cluster.yaml

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
	generate-ray-cluster deploy-ray-cluster delete-ray-cluster \
	install-kuberay status list-clusters list-services list-jobs list-all \
	watch-logs describe upgrade uninstall clean-namespace show-values get-values
