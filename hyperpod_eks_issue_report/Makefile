# HyperPod EKS Issue Report Collector Makefile

.PHONY: help install run clean test

# Configuration
CLUSTER ?= my-hyperpod-cluster
S3_PATH ?= s3://my-diagnostics-bucket
INSTANCE_GROUP ?=
MAX_WORKERS ?= 10

# Default target
help:
	@echo "Available targets:"
	@echo "  install           - Install Python dependencies"
	@echo "  run               - Run issue report collector (requires CLUSTER and S3_PATH)"
	@echo "  run-nvidia        - Collect nvidia-smi from all nodes"
	@echo "  run-system        - Collect system health information"
	@echo "  run-k8s           - Collect Kubernetes status"
	@echo "  run-network       - Collect network diagnostics"
	@echo "  run-custom        - Run with custom commands (set COMMANDS)"
	@echo "  clean             - Clean up temporary files"
	@echo "  test              - Run basic tests"
	@echo ""
	@echo "Configuration variables:"
	@echo "  CLUSTER           - HyperPod cluster name (required)"
	@echo "  S3_PATH           - S3 path for reports (required, e.g., s3://bucket/prefix)"
	@echo "  INSTANCE_GROUP    - Target specific instance group (optional)"
	@echo "  MAX_WORKERS       - Max concurrent workers (default: 10)"
	@echo ""
	@echo "Examples:"
	@echo "  make run CLUSTER=my-cluster S3_PATH=s3://my-bucket"
	@echo "  make run-system CLUSTER=my-cluster S3_PATH=s3://my-bucket/diagnostics"
	@echo "  make run CLUSTER=my-cluster S3_PATH=s3://my-bucket INSTANCE_GROUP=worker-group"

# Install dependencies
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt

# Generic run target - runs with default nvidia-smi and EKS log collector
run:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@echo "Collecting reports from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-path $(S3_PATH) \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with nvidia-smi (already included by default, but can add more GPU commands)
run-nvidia:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@echo "Collecting nvidia-smi from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-path $(S3_PATH) \
		--command "nvidia-smi -q" \
		--command "nvidia-smi topo -m" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with system health commands
run-system:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@echo "Collecting system health from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-path $(S3_PATH) \
		--command "uptime" \
		--command "free -h" \
		--command "df -h" \
		--command "top -bn1 | head -20" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with Kubernetes commands
run-k8s:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@echo "Collecting Kubernetes status from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-path $(S3_PATH) \
		--command "kubectl get nodes" \
		--command "kubectl get pods --all-namespaces" \
		--command "kubectl top nodes" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with network diagnostics
run-network:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@echo "Collecting network diagnostics from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-path $(S3_PATH) \
		--command "ip addr show" \
		--command "ip route show" \
		--command "ss -tulpn" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with custom commands
run-custom:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@if [ -z "$(COMMANDS)" ]; then echo "Error: COMMANDS not set. Example: COMMANDS='df -h,free -h'"; exit 1; fi
	@echo "Running custom commands on cluster: $(CLUSTER)"
	@CMD_ARGS=""; \
	IFS=',' read -ra CMDS <<< "$(COMMANDS)"; \
	for cmd in "$${CMDS[@]}"; do \
		CMD_ARGS="$$CMD_ARGS --command \"$$cmd\""; \
	done; \
	eval python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-path $(S3_PATH) \
		$$CMD_ARGS \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Clean up
clean:
	@echo "Cleaning up temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/

# Basic test
test:
	@echo "Running basic tests..."
	python -c "import boto3; print('boto3 OK')"
	python -c "from hyperpod_eks_issue_report import HyperPodEKSIssueReportCollector; print('Import OK')"
	@echo "Tests passed!"

# Check AWS credentials
check-aws:
	@echo "Checking AWS credentials..."
	aws sts get-caller-identity
	@echo "AWS credentials OK!"

# Check S3 path access
check-s3:
	@if [ -z "$(S3_PATH)" ]; then echo "Error: S3_PATH not set"; exit 1; fi
	@echo "Checking S3 path access: $(S3_PATH)"
	@BUCKET=$$(echo $(S3_PATH) | sed 's|s3://||' | cut -d'/' -f1); \
	aws s3 ls s3://$$BUCKET/ || echo "Warning: Cannot access bucket"
