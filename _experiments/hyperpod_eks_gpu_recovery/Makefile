.PHONY: help check-nodes check-plugin-pods check-gpu-health check-allocatable check-plugin-logs \
       inject-error clear-error restart-plugin \
       install-operator uninstall-operator \
       deploy-test-pod delete-test-pod cleanup

# --- Configuration ---
GPU_NODE ?= $(shell kubectl get nodes -o jsonpath='{range .items[?(@.status.allocatable.nvidia\.com/gpu)]}{.metadata.name}{"\n"}{end}' 2>/dev/null | head -1)
GPU_ID ?= 0
XID_VALUE ?= 94
DCGM_FIELD_XID ?= 230
NODE_COLUMNS ?= NAME:.metadata.name,INSTANCETYPE:.metadata.labels.node\.kubernetes\.io/instance-type,GPU:.status.allocatable.nvidia\.com/gpu,EFA:.status.allocatable.vpc\.amazonaws\.com/efa,HEALTH:.metadata.labels.sagemaker\.amazonaws\.com/node-health-status

# Device plugin pod selectors
PLUGIN_NS ?= kube-system
PLUGIN_LABEL ?= app.kubernetes.io/name=nvidia-device-plugin

# SSM target components (derived from node labels)
CLUSTER_NAME ?= $(shell kubectl get node $(GPU_NODE) -o jsonpath='{.metadata.labels.sagemaker\.amazonaws\.com/cluster-name}' 2>/dev/null)
CLUSTER_ID ?= $(shell aws sagemaker describe-cluster --cluster-name $(CLUSTER_NAME) --query 'ClusterArn' --output text 2>/dev/null | awk -F/ '{print $$NF}')
INSTANCE_GROUP ?= $(shell kubectl get node $(GPU_NODE) -o jsonpath='{.metadata.labels.sagemaker\.amazonaws\.com/instance-group-name}' 2>/dev/null)
INSTANCE_ID ?= $(shell echo $(GPU_NODE) | grep -o 'i-[a-f0-9]\+')
SSM_TARGET ?= sagemaker-cluster:$(CLUSTER_ID)_$(INSTANCE_GROUP)-$(INSTANCE_ID)

# GPU Operator (Phase 2)
OPERATOR_NAMESPACE ?= gpu-operator

# Helper: run a command on the node via SSM
define SSM_CMD
aws ssm start-session \
  --target "$(SSM_TARGET)" \
  --document-name AWS-StartNonInteractiveCommand \
  --parameters '{"command":["$(1)"]}'
endef

help:
	@echo "HyperPod EKS GPU Recovery Experiment"
	@echo ""
	@echo "Pre-checks:"
	@echo "  make check-nodes          - List GPU nodes and allocatable GPUs"
	@echo "  make check-plugin-pods    - List device plugin pods"
	@echo "  make check-gpu-health     - Check DCGM health status on GPU_NODE (via SSM)"
	@echo "  make check-allocatable    - Show allocatable nvidia.com/gpu on GPU_NODE"
	@echo "  make check-plugin-logs    - Tail device plugin logs for XID events"
	@echo ""
	@echo "Error Injection (Phase 1 & 2):"
	@echo "  make inject-error         - Inject Xid $(XID_VALUE) on GPU_ID via DCGM (SSM)"
	@echo "  make clear-error          - Clear injected XID error on GPU_ID (SSM)"
	@echo "  make restart-plugin       - Restart device plugin pod on GPU_NODE"
	@echo ""
	@echo "GPU Operator (Phase 2):"
	@echo "  make install-operator     - Install NVIDIA GPU Operator via Helm"
	@echo "  make uninstall-operator   - Uninstall NVIDIA GPU Operator"
	@echo ""
	@echo "Test Workload:"
	@echo "  make deploy-test-pod      - Deploy a simple GPU test pod"
	@echo "  make delete-test-pod      - Delete the GPU test pod"
	@echo ""
	@echo "Cleanup:"
	@echo "  make cleanup              - Remove all test resources"
	@echo ""
	@echo "Configuration (override with env vars):"
	@echo "  GPU_NODE=$(GPU_NODE)"
	@echo "  GPU_ID=$(GPU_ID)"
	@echo "  XID_VALUE=$(XID_VALUE)"
	@echo "  SSM_TARGET=$(SSM_TARGET)"

# ============================================================
# Pre-checks
# ============================================================

check-nodes:
	@echo "=== GPU Nodes ==="
	kubectl get nodes -o=custom-columns='$(NODE_COLUMNS)'
	@echo ""
	@echo "=== Target Node: $(GPU_NODE) ==="
	@echo "=== SSM Target:  $(SSM_TARGET) ==="

check-plugin-pods:
	@echo "=== Device Plugin Pods ($(PLUGIN_NS) / $(PLUGIN_LABEL)) ==="
	kubectl get pods -n $(PLUGIN_NS) -l $(PLUGIN_LABEL) -o wide

check-gpu-health:
	@echo "=== DCGM Health Check on $(GPU_NODE) via SSM ==="
	@echo "SSM Target: $(SSM_TARGET)"
	@$(call SSM_CMD,dcgmi health -g 0 -s a)
	@$(call SSM_CMD,dcgmi health -g 0 -c)

check-allocatable:
	@echo "=== Allocatable GPUs on $(GPU_NODE) ==="
	@echo -n "Allocatable: "
	@kubectl get node $(GPU_NODE) -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
	@echo ""
	@echo -n "Capacity:    "
	@kubectl get node $(GPU_NODE) -o jsonpath='{.status.capacity.nvidia\.com/gpu}'
	@echo ""

check-plugin-logs:
	@echo "=== Device Plugin Logs on $(GPU_NODE) (last 50 lines) ==="
	@POD=$$(kubectl get pods -n $(PLUGIN_NS) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No device plugin pod found on $(GPU_NODE) in namespace $(PLUGIN_NS)."; \
		exit 1; \
	fi; \
	echo "Pod: $(PLUGIN_NS)/$$POD"; \
	kubectl logs -n $(PLUGIN_NS) $$POD --tail=50

# ============================================================
# Error Injection (Xid 94 via DCGM field 230, over SSM)
# ============================================================

inject-error:
	@echo "=== Injecting Xid $(XID_VALUE) on GPU $(GPU_ID) @ $(GPU_NODE) ==="
	@echo "DCGM Field $(DCGM_FIELD_XID) = DCGM_FI_DEV_XID_ERRORS, value = $(XID_VALUE)"
	@echo "SSM Target: $(SSM_TARGET)"
	@echo ""
	@$(call SSM_CMD,dcgmi test --inject --gpuid $(GPU_ID) -f $(DCGM_FIELD_XID) -v $(XID_VALUE))
	@echo ""
	@echo "Xid $(XID_VALUE) injected. Next steps:"
	@echo "  make check-plugin-logs    # Verify device plugin detected XidCriticalError"
	@echo "  make check-allocatable    # Confirm GPU count dropped"

clear-error:
	@echo "=== Clearing XID Error on GPU $(GPU_ID) @ $(GPU_NODE) ==="
	@echo "SSM Target: $(SSM_TARGET)"
	@$(call SSM_CMD,dcgmi test --inject --gpuid $(GPU_ID) -f $(DCGM_FIELD_XID) -v 0)
	@echo ""
	@echo "XID error cleared. Next steps:"
	@echo "  make check-plugin-logs    # Check if device plugin noticed the clear"
	@echo "  make check-allocatable    # Check if GPU count recovered"
	@echo "  (wait 30-60s and re-check — device plugin polls periodically)"

# ============================================================
# Device Plugin Restart
# ============================================================

restart-plugin:
	@echo "=== Restarting Device Plugin Pod on $(GPU_NODE) ==="
	@POD=$$(kubectl get pods -n $(PLUGIN_NS) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No device plugin pod found on $(GPU_NODE) in namespace $(PLUGIN_NS)."; \
		exit 1; \
	fi; \
	echo "Deleting pod: $(PLUGIN_NS)/$$POD (DaemonSet will recreate it)"; \
	kubectl delete pod -n $(PLUGIN_NS) $$POD
	@echo ""
	@echo "Waiting for new pod to be ready..."
	@sleep 10
	kubectl get pods -n $(PLUGIN_NS) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o wide

# ============================================================
# GPU Operator
# ============================================================

install-operator:
	@echo "=== Installing NVIDIA GPU Operator ==="
	helm repo add nvidia https://helm.ngc.nvidia.com/nvidia || true
	helm repo update
	helm install gpu-operator nvidia/gpu-operator \
		--namespace $(OPERATOR_NAMESPACE) \
		--create-namespace \
		--set driver.enabled=false \
		--set toolkit.enabled=true \
		--set devicePlugin.enabled=true \
		--set dcgm.enabled=true \
		--set dcgmExporter.enabled=true
	@echo ""
	@echo "GPU Operator installed. Wait for pods to be ready:"
	@echo "  kubectl get pods -n $(OPERATOR_NAMESPACE) -w"

uninstall-operator:
	@echo "=== Uninstalling NVIDIA GPU Operator ==="
	helm uninstall gpu-operator -n $(OPERATOR_NAMESPACE) || true
	kubectl delete namespace $(OPERATOR_NAMESPACE) --ignore-not-found
	@echo "GPU Operator uninstalled."

# ============================================================
# Test Workload
# ============================================================

deploy-test-pod:
	@echo "=== Deploying GPU Test Pod ==="
	@kubectl apply -f - <<'EOF'
	apiVersion: v1
	kind: Pod
	metadata:
	  name: gpu-recovery-test
	spec:
	  restartPolicy: Never
	  containers:
	  - name: cuda-test
	    image: nvcr.io/nvidia/cuda:12.2.0-base-ubuntu22.04
	    command: ["nvidia-smi", "-l", "5"]
	    resources:
	      limits:
	        nvidia.com/gpu: 1
	EOF
	@echo "Pod deployed. Check status: kubectl get pod gpu-recovery-test"

delete-test-pod:
	kubectl delete pod gpu-recovery-test --ignore-not-found

# ============================================================
# Cleanup
# ============================================================

cleanup: delete-test-pod
	@echo "=== Cleanup Complete ==="
