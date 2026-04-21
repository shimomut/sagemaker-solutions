.PHONY: help check-nodes check-plugin-pods check-gpu-health check-allocatable check-plugin-logs \
       inject-error clear-error restart-plugin \
       install-operator uninstall-operator \
       deploy-test-pod delete-test-pod cleanup

# --- Configuration ---
GPU_NODE ?= $(shell kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
GPU_ID ?= 0
NAMESPACE ?= kube-system
OPERATOR_NAMESPACE ?= gpu-operator
XID_VALUE ?= 94
DCGM_FIELD_XID ?= 230
PLUGIN_LABEL ?= app=nvidia-device-plugin-daemonset

help:
	@echo "HyperPod EKS GPU Recovery Experiment"
	@echo ""
	@echo "Pre-checks:"
	@echo "  make check-nodes          - List GPU nodes and allocatable GPUs"
	@echo "  make check-plugin-pods    - List device plugin DaemonSet pods"
	@echo "  make check-gpu-health     - Check DCGM health status on GPU_NODE"
	@echo "  make check-allocatable    - Show allocatable nvidia.com/gpu on GPU_NODE"
	@echo "  make check-plugin-logs    - Tail device plugin logs for XID events"
	@echo ""
	@echo "Error Injection (Phase 1 & 2):"
	@echo "  make inject-error         - Inject Xid $(XID_VALUE) on GPU_ID via DCGM"
	@echo "  make clear-error          - Clear injected XID error on GPU_ID"
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
	@echo "  NAMESPACE=$(NAMESPACE)"

# ============================================================
# Pre-checks
# ============================================================

check-nodes:
	@echo "=== GPU Nodes ==="
	kubectl get nodes -l nvidia.com/gpu.present=true -o wide
	@echo ""
	@echo "=== Allocatable GPUs per Node ==="
	kubectl get nodes -l nvidia.com/gpu.present=true -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'

check-plugin-pods:
	@echo "=== Device Plugin Pods ==="
	kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) -o wide 2>/dev/null || \
	kubectl get pods -n $(NAMESPACE) -l app.kubernetes.io/name=nvidia-device-plugin -o wide 2>/dev/null || \
	kubectl get pods -n $(OPERATOR_NAMESPACE) -l app=nvidia-device-plugin-daemonset -o wide 2>/dev/null || \
	echo "No device plugin pods found. Check labels or namespace."

check-gpu-health:
	@echo "=== DCGM Health Check on $(GPU_NODE) ==="
	@POD=$$(kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "No device plugin pod found on $(GPU_NODE). Trying dcgm-exporter..."; \
		POD=$$(kubectl get pods -n $(NAMESPACE) -l app=dcgm-exporter --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	fi; \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No suitable pod found on $(GPU_NODE) to run dcgmi."; \
		echo "You may need to exec into a node directly:"; \
		echo "  kubectl debug node/$(GPU_NODE) -it --image=nvcr.io/nvidia/cloud-native/dcgm:3.3.0-1-ubuntu22.04"; \
	else \
		echo "Using pod: $$POD"; \
		kubectl exec -n $(NAMESPACE) $$POD -- dcgmi health -g 0 -c 2>/dev/null || \
		echo "dcgmi not available in this pod. Try a debug pod with DCGM installed."; \
	fi

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
	@POD=$$(kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No device plugin pod found on $(GPU_NODE)."; \
		exit 1; \
	fi; \
	echo "Pod: $$POD"; \
	kubectl logs -n $(NAMESPACE) $$POD --tail=50

# ============================================================
# Error Injection (Xid 94 via DCGM field 230)
# ============================================================

inject-error:
	@echo "=== Injecting Xid $(XID_VALUE) on GPU $(GPU_ID) @ $(GPU_NODE) ==="
	@echo "DCGM Field $(DCGM_FIELD_XID) = DCGM_FI_DEV_XID_ERRORS, value = $(XID_VALUE)"
	@echo ""
	@POD=$$(kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No device plugin pod found on $(GPU_NODE)."; \
		exit 1; \
	fi; \
	echo "Using pod: $$POD"; \
	kubectl exec -n $(NAMESPACE) $$POD -- dcgmi test --inject --gpuid $(GPU_ID) -f $(DCGM_FIELD_XID) -v $(XID_VALUE)
	@echo ""
	@echo "Xid $(XID_VALUE) injected. Next steps:"
	@echo "  make check-plugin-logs    # Verify device plugin detected XidCriticalError"
	@echo "  make check-allocatable    # Confirm GPU count dropped"

clear-error:
	@echo "=== Clearing XID Error on GPU $(GPU_ID) @ $(GPU_NODE) ==="
	@POD=$$(kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No device plugin pod found on $(GPU_NODE)."; \
		exit 1; \
	fi; \
	echo "Using pod: $$POD"; \
	kubectl exec -n $(NAMESPACE) $$POD -- dcgmi test --inject --gpuid $(GPU_ID) -f $(DCGM_FIELD_XID) -v 0
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
	@POD=$$(kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
	if [ -z "$$POD" ]; then \
		echo "ERROR: No device plugin pod found on $(GPU_NODE)."; \
		exit 1; \
	fi; \
	echo "Deleting pod: $$POD (DaemonSet will recreate it)"; \
	kubectl delete pod -n $(NAMESPACE) $$POD
	@echo ""
	@echo "Waiting for new pod to be ready..."
	@sleep 10
	kubectl get pods -n $(NAMESPACE) -l $(PLUGIN_LABEL) --field-selector spec.nodeName=$(GPU_NODE) -o wide

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
	  nodeSelector:
	    nvidia.com/gpu.present: "true"
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
