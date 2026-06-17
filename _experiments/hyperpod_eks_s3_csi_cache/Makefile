SHELL := /bin/bash

# =============================================================================
# Configuration — override on the command line, e.g.
#   make install-driver S3_BUCKET_NAME=my-bucket EKS_CLUSTER_NAME=my-cluster
# or export them in your shell / a local env file.
# =============================================================================

# --- Cluster / AWS ---
EKS_CLUSTER_NAME ?= sagemaker-k8-1-1bd2626f-eks
AWS_REGION       ?= us-west-2
AWS_ACCOUNT_ID   ?= 842413447717

# --- HyperPod cluster (for the Option A lifecycle-script automation) ---
HYPERPOD_CLUSTER_NAME ?= k8-1
NVME_INSTANCE_GROUP   ?= worker3      # the NVMe instance group to relocate kubelet onto

# --- S3 bucket the cache reads from (REQUIRED for most targets) ---
S3_BUCKET_NAME   ?=

# --- IAM names created by the install script ---
S3_CSI_ROLE_NAME ?= SM_HP_S3_CSI_ROLE
S3_POLICY_NAME   ?= S3MountpointAccessPolicy
READ_ONLY        ?= true       # true = grant read-only S3 permissions

# --- PV / PVC ---
NAMESPACE        ?= default
PV_NAME          ?= s3-training-data-pv
PVC_NAME         ?= s3-training-data-pvc
VOLUME_HANDLE    ?= s3-training-data-volume

# --- Option A: emptyDir cache (NVMe via kubelet symlink) ---
CACHE_SIZE_LIMIT ?= 100Gi

# --- Option B: ephemeral cache on the DLAMI NVMe filesystem (hostDir mode) ---
NVME_STORAGE_CLASS      ?= nvme-cache
CACHE_EPHEMERAL_REQUEST ?= 100Gi

# --- Test pod ---
TEST_POD_NAME      ?= s3-cache-test
TEST_IMAGE         ?= public.ecr.aws/docker/library/ubuntu:22.04
TEST_INSTANCE_TYPE ?= ml.g6.8xlarge

# --- Mountpoint Pods namespace (per-volume pods spawned by the CSI driver v2) ---
MOUNT_S3_NAMESPACE ?= mount-s3

MANIFESTS := manifests
RENDER    := python3 scripts/render.py

# Export all of the above so scripts/render.py and helper scripts can see them.
export

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================
.PHONY: help
help:
	@echo "Mountpoint for S3 CSI driver — local NVMe cache on HyperPod EKS"
	@echo ""
	@echo "Driver setup:"
	@echo "  install-driver        Install the S3 CSI driver add-on (IAM OIDC, policy, role, addon)"
	@echo "  verify-driver         Show CSI driver pods and registration"
	@echo "  uninstall-driver      Remove the add-on (set DELETE_IAM=true to also remove IAM)"
	@echo ""
	@echo "Option A — emptyDir cache on NVMe (recommended starting point):"
	@echo "  lcc-set-auto          Edit LCC: prefer NVMe (/opt/dlami/nvme), fall back to EBS if absent"
	@echo "  lcc-set-nvme          Edit LCC: force kubelet data root -> /opt/dlami/nvme"
	@echo "  lcc-revert-ebs        Edit LCC: force kubelet data root -> /opt/sagemaker (EBS)"
	@echo "  lcc-replace-nodes     Edit LCC (auto) AND replace the $(NVME_INSTANCE_GROUP) nodes (DESTRUCTIVE)"
	@echo "  deploy-a              Apply PV (emptyDir cache) + PVC"
	@echo "  delete-a              Delete PV + PVC"
	@echo ""
	@echo "Option B — ephemeral cache on the DLAMI NVMe (no lifecycle edit / node recreation):"
	@echo "  install-nvme-cache         Deploy setup DaemonSet + Local Volume Static Provisioner (nvme-cache SC)"
	@echo "  delete-nvme-cache          Remove the provisioner + setup DaemonSet"
	@echo "  deploy-b                   Apply PV (ephemeral cache) + PVC"
	@echo "  delete-b                   Delete PV + PVC"
	@echo ""
	@echo "Test & verify:"
	@echo "  deploy-test-pod       Launch a pod that mounts the bucket at /data"
	@echo "  delete-test-pod       Remove the test pod"
	@echo "  verify-mount          ls + df inside the test pod"
	@echo "  benchmark             Time a cold vs warm read of a file from /data"
	@echo "  mountpoint-pods       List the CSI node daemonset and per-volume Mountpoint pods"
	@echo "  mountpoint-logs       Tail logs from the Mountpoint pods"
	@echo "  status                Show PV/PVC/test-pod status"
	@echo ""
	@echo "Current config: cluster=$(EKS_CLUSTER_NAME) region=$(AWS_REGION) bucket=$(S3_BUCKET_NAME)"

# =============================================================================
# Guards
# =============================================================================
.PHONY: guard-bucket
guard-bucket:
	@if [[ -z "$(S3_BUCKET_NAME)" ]]; then \
		echo "ERROR: S3_BUCKET_NAME is not set. Run: make <target> S3_BUCKET_NAME=your-bucket"; \
		exit 1; \
	fi

# =============================================================================
# Driver installation
# =============================================================================
.PHONY: install-driver
install-driver: guard-bucket
	bash scripts/install_s3_csi_driver.sh

.PHONY: verify-driver
verify-driver:
	@echo "=== s3-csi-node DaemonSet (kube-system) ==="
	@kubectl get pods -n kube-system -l app=s3-csi-node -o wide || true
	@echo ""
	@echo "=== Registered CSI drivers ==="
	@kubectl get csidrivers | grep -E 'NAME|s3' || echo "s3.csi.aws.com not found"

.PHONY: uninstall-driver
uninstall-driver:
	bash scripts/uninstall_s3_csi_driver.sh

# =============================================================================
# Option A — emptyDir cache on NVMe
# =============================================================================
.PHONY: lcc-set-auto
lcc-set-auto:
	python3 scripts/update_lifecycle_nvme.py \
		--cluster-name $(HYPERPOD_CLUSTER_NAME) --region $(AWS_REGION) --target auto

.PHONY: lcc-set-nvme
lcc-set-nvme:
	python3 scripts/update_lifecycle_nvme.py \
		--cluster-name $(HYPERPOD_CLUSTER_NAME) --region $(AWS_REGION) --target nvme

.PHONY: lcc-revert-ebs
lcc-revert-ebs:
	python3 scripts/update_lifecycle_nvme.py \
		--cluster-name $(HYPERPOD_CLUSTER_NAME) --region $(AWS_REGION) --target ebs

# DESTRUCTIVE: edits the LCC (auto NVMe-with-EBS-fallback), then replaces the NVMe
# node group so the updated script re-runs. Prompts for confirmation (CONFIRM=yes to skip).
.PHONY: lcc-replace-nodes
lcc-replace-nodes:
	python3 scripts/update_lifecycle_nvme.py \
		--cluster-name $(HYPERPOD_CLUSTER_NAME) --region $(AWS_REGION) --target auto \
		--replace-nodes --instance-group $(NVME_INSTANCE_GROUP) \
		$(if $(filter yes,$(CONFIRM)),--yes,)

.PHONY: deploy-a
deploy-a: guard-bucket
	$(RENDER) $(MANIFESTS)/pv-option-a.yaml | kubectl apply -f -
	$(RENDER) $(MANIFESTS)/pvc.yaml | kubectl apply -f -
	@echo "Option A deployed. Check binding with: make status"

.PHONY: delete-a
delete-a:
	-$(RENDER) $(MANIFESTS)/pvc.yaml | kubectl delete -f - --ignore-not-found
	-$(RENDER) $(MANIFESTS)/pv-option-a.yaml | kubectl delete -f - --ignore-not-found

# =============================================================================
# Option B — ephemeral cache on the DLAMI NVMe filesystem (hostDir mode)
# =============================================================================
.PHONY: install-nvme-cache
install-nvme-cache:
	kubectl apply -f $(MANIFESTS)/nvme-cache-setup-daemonset.yaml
	kubectl apply -f $(MANIFESTS)/nvme-cache-provisioner.yaml
	@echo "Deployed. Once the setup DaemonSet and provisioner are running, verify PVs with:"
	@echo "  kubectl get pv | grep $(NVME_STORAGE_CLASS)"

.PHONY: delete-nvme-cache
delete-nvme-cache:
	kubectl delete -f $(MANIFESTS)/nvme-cache-provisioner.yaml --ignore-not-found
	kubectl delete -f $(MANIFESTS)/nvme-cache-setup-daemonset.yaml --ignore-not-found

.PHONY: deploy-b
deploy-b: guard-bucket
	$(RENDER) $(MANIFESTS)/pv-option-b.yaml | kubectl apply -f -
	$(RENDER) $(MANIFESTS)/pvc.yaml | kubectl apply -f -
	@echo "Option B deployed. Check binding with: make status"

.PHONY: delete-b
delete-b:
	-$(RENDER) $(MANIFESTS)/pvc.yaml | kubectl delete -f - --ignore-not-found
	-$(RENDER) $(MANIFESTS)/pv-option-b.yaml | kubectl delete -f - --ignore-not-found

# =============================================================================
# Test & verify
# =============================================================================
.PHONY: deploy-test-pod
deploy-test-pod: guard-bucket
	$(RENDER) $(MANIFESTS)/test-pod.yaml | kubectl apply -f -
	@echo "Waiting for $(TEST_POD_NAME) to be ready..."
	@kubectl wait --for=condition=ready pod/$(TEST_POD_NAME) -n $(NAMESPACE) --timeout=180s || \
		kubectl describe pod/$(TEST_POD_NAME) -n $(NAMESPACE)

.PHONY: delete-test-pod
delete-test-pod:
	-$(RENDER) $(MANIFESTS)/test-pod.yaml | kubectl delete -f - --ignore-not-found

.PHONY: verify-mount
verify-mount:
	@echo "=== ls /data ==="
	@kubectl exec -n $(NAMESPACE) $(TEST_POD_NAME) -- ls -la /data | head -n 20
	@echo "=== df -h /data ==="
	@kubectl exec -n $(NAMESPACE) $(TEST_POD_NAME) -- df -h /data

.PHONY: benchmark
benchmark:
	@echo "Timing cold vs warm read of the first file under /data..."
	@kubectl exec -n $(NAMESPACE) $(TEST_POD_NAME) -- /bin/sh -c '\
		f=$$(find /data -type f 2>/dev/null | head -n 1); \
		if [ -z "$$f" ]; then echo "No files found under /data"; exit 1; fi; \
		echo "File: $$f"; \
		echo "--- cold read (populates cache) ---"; \
		time cat "$$f" > /dev/null; \
		echo "--- warm read (served from local NVMe cache) ---"; \
		time cat "$$f" > /dev/null'

.PHONY: mountpoint-pods
mountpoint-pods:
	@echo "=== s3-csi-node DaemonSet (kube-system) ==="
	@kubectl get pods -n kube-system -l app=s3-csi-node -o wide || true
	@echo ""
	@echo "=== Per-volume Mountpoint pods ($(MOUNT_S3_NAMESPACE)) ==="
	@kubectl get pods -n $(MOUNT_S3_NAMESPACE) -o wide 2>/dev/null || \
		echo "  (namespace $(MOUNT_S3_NAMESPACE) not present — older driver versions run mounts differently)"

.PHONY: mountpoint-logs
mountpoint-logs:
	@kubectl logs -n $(MOUNT_S3_NAMESPACE) -l s3.csi.aws.com/type --tail=100 2>/dev/null || \
		kubectl logs -n kube-system -l app=s3-csi-node --tail=100 --max-log-requests=10

.PHONY: status
status:
	@echo "=== PV ==="
	@kubectl get pv $(PV_NAME) -o wide 2>/dev/null || echo "  $(PV_NAME) not found"
	@echo "=== PVC ==="
	@kubectl get pvc $(PVC_NAME) -n $(NAMESPACE) -o wide 2>/dev/null || echo "  $(PVC_NAME) not found"
	@echo "=== Test pod ==="
	@kubectl get pod $(TEST_POD_NAME) -n $(NAMESPACE) -o wide 2>/dev/null || echo "  $(TEST_POD_NAME) not found"

# =============================================================================
# Convenience: render manifests to stdout without applying (debugging)
# =============================================================================
.PHONY: render-a render-b
render-a: guard-bucket
	@$(RENDER) $(MANIFESTS)/pv-option-a.yaml
	@echo "---"
	@$(RENDER) $(MANIFESTS)/pvc.yaml

render-b: guard-bucket
	@$(RENDER) $(MANIFESTS)/pv-option-b.yaml
	@echo "---"
	@$(RENDER) $(MANIFESTS)/pvc.yaml
