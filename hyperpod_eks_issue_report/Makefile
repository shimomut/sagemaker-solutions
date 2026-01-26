# HyperPod EKS Issue Report Collector Makefile

.PHONY: help install run clean test

# Configuration
CLUSTER ?= my-hyperpod-cluster
S3_BUCKET ?= my-diagnostics-bucket
S3_PREFIX ?= hyperpod-issue-reports
INSTANCE_GROUP ?=
MAX_WORKERS ?= 10

# Default target
help:
	@echo "Available targets:"
	@echo "  install           - Install Python dependencies"
	@echo "  run               - Run issue report collector (requires CLUSTER and S3_BUCKET)"
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
	@echo "  S3_BUCKET         - S3 bucket for reports (required)"
	@echo "  S3_PREFIX         - S3 prefix (default: hyperpod-issue-reports)"
	@echo "  INSTANCE_GROUP    - Target specific instance group (optional)"
	@echo "  MAX_WORKERS       - Max concurrent workers (default: 10)"
	@echo ""
	@echo "Examples:"
	@echo "  make run-nvidia CLUSTER=my-cluster S3_BUCKET=my-bucket"
	@echo "  make run-system CLUSTER=my-cluster S3_BUCKET=my-bucket INSTANCE_GROUP=worker-group"

# Install dependencies
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt

# Run with nvidia-smi
run-nvidia:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@echo "Collecting nvidia-smi from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-bucket $(S3_BUCKET) \
		--s3-prefix $(S3_PREFIX) \
		--command "nvidia-smi" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with system health commands
run-system:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@echo "Collecting system health from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-bucket $(S3_BUCKET) \
		--s3-prefix $(S3_PREFIX) \
		--command "uptime" \
		--command "free -h" \
		--command "df -h" \
		--command "top -bn1 | head -20" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with Kubernetes commands
run-k8s:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@echo "Collecting Kubernetes status from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-bucket $(S3_BUCKET) \
		--s3-prefix $(S3_PREFIX) \
		--command "kubectl get nodes" \
		--command "kubectl get pods --all-namespaces" \
		--command "kubectl top nodes" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with network diagnostics
run-network:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@echo "Collecting network diagnostics from cluster: $(CLUSTER)"
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-bucket $(S3_BUCKET) \
		--s3-prefix $(S3_PREFIX) \
		--command "ip addr show" \
		--command "ip route show" \
		--command "ss -tulpn" \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Run with custom commands
run-custom:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@if [ -z "$(COMMANDS)" ]; then echo "Error: COMMANDS not set. Example: COMMANDS='nvidia-smi,df -h'"; exit 1; fi
	@echo "Running custom commands on cluster: $(CLUSTER)"
	@CMD_ARGS=""; \
	IFS=',' read -ra CMDS <<< "$(COMMANDS)"; \
	for cmd in "$${CMDS[@]}"; do \
		CMD_ARGS="$$CMD_ARGS --command \"$$cmd\""; \
	done; \
	python hyperpod_eks_issue_report.py \
		--cluster $(CLUSTER) \
		--s3-bucket $(S3_BUCKET) \
		--s3-prefix $(S3_PREFIX) \
		$$CMD_ARGS \
		$(if $(INSTANCE_GROUP),--instance-group $(INSTANCE_GROUP),) \
		--max-workers $(MAX_WORKERS)

# Generic run target
run:
	@if [ -z "$(CLUSTER)" ]; then echo "Error: CLUSTER not set"; exit 1; fi
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@echo "Usage: Use specific targets like run-nvidia, run-system, etc."
	@echo "Or use run-custom with COMMANDS='cmd1,cmd2'"

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

# Check S3 bucket access
check-s3:
	@if [ -z "$(S3_BUCKET)" ]; then echo "Error: S3_BUCKET not set"; exit 1; fi
	@echo "Checking S3 bucket access: $(S3_BUCKET)"
	aws s3 ls s3://$(S3_BUCKET)/ || echo "Warning: Cannot access bucket"
