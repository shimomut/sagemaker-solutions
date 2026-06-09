SHELL := /bin/bash

# EKS-side troubleshooting cases. Run from a workstation whose kubectl
# context points at the HyperPod EKS cluster.
#
# Variables:
#   CONFIRM=1            actually trigger (default: dry-run)
#   NAMESPACE            k8s namespace (default: hp-troubleshoot)

CONFIRM ?= 0
NAMESPACE ?= hp-troubleshoot

K = kubectl -n $(NAMESPACE)

.PHONY: sanity-check ensure-ns
.PHONY: case-1 case-1-revert
.PHONY: case-2 case-2-revert
.PHONY: case-3 case-3-revert
.PHONY: case-4 case-4-revert
.PHONY: case-5 case-5-revert

sanity-check:
	@echo "=== EKS sanity check ==="
	@kubectl version --short 2>/dev/null || kubectl version
	@echo ""
	@echo "Current context: $$(kubectl config current-context)"
	@echo ""
	@kubectl get nodes
	@echo ""
	@kubectl get nodes -o jsonpath='{.items[*].status.allocatable.nvidia\.com/gpu}{"\n"}' \
	  | tr ' ' '\n' | awk '{s+=$$1} END {print "Total nvidia.com/gpu allocatable: "s}'

ensure-ns:
	@kubectl get ns $(NAMESPACE) >/dev/null 2>&1 || kubectl create ns $(NAMESPACE)

# Each case body is a single shell invocation so the CONFIRM gate's `exit 0`
# actually short-circuits the destructive commands. ensure-ns is inlined into
# each case body for the same reason — otherwise a dry-run would still create
# the namespace as a side-effect of the prerequisite.

define ensure_ns_inline
kubectl get ns $(NAMESPACE) >/dev/null 2>&1 || kubectl create ns $(NAMESPACE);
endef

# ============================================================================
# Case 1: Pod OOMKilled
# Skill: hyperpod-nccl
# Prompt: "My pod keeps getting OOMKilled, diagnose it"
# ============================================================================

case-1:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [eks case-1: pod OOMKilled]. CONFIRM=1 to apply."; \
	  exit 0; \
	fi; \
	set -e; \
	$(ensure_ns_inline) \
	echo "=== EKS case 1: deploy pod that allocates 256Mi against 64Mi limit ==="; \
	$(K) apply -f manifests/case-1-oom.yaml; \
	sleep 5; \
	$(K) get pod oom-pod -o wide || true

case-1-revert:
	-$(K) delete -f manifests/case-1-oom.yaml --ignore-not-found

# ============================================================================
# Case 2: CrashLoopBackOff (entrypoint exits 1)
# Skill: hyperpod-nccl
# Prompt: "A pod is stuck in CrashLoopBackOff, what's wrong?"
# ============================================================================

case-2:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [eks case-2: CrashLoopBackOff]. CONFIRM=1 to apply."; \
	  exit 0; \
	fi; \
	set -e; \
	$(ensure_ns_inline) \
	echo "=== EKS case 2: deploy pod that always exits 1 ==="; \
	$(K) apply -f manifests/case-2-crashloop.yaml; \
	sleep 10; \
	$(K) get pod crashloop-pod -o wide || true

case-2-revert:
	-$(K) delete -f manifests/case-2-crashloop.yaml --ignore-not-found

# ============================================================================
# Case 3: Pod stuck Pending — requests 999 GPUs
# Skill: hyperpod-nccl / hyperpod-cluster-debugger
# Prompt: "My GPU pod is stuck Pending, why?"
# ============================================================================

case-3:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [eks case-3: Pending unschedulable]. CONFIRM=1 to apply."; \
	  exit 0; \
	fi; \
	set -e; \
	$(ensure_ns_inline) \
	echo "=== EKS case 3: deploy pod requesting 999 nvidia.com/gpu ==="; \
	$(K) apply -f manifests/case-3-pending.yaml; \
	sleep 5; \
	$(K) get pod pending-gpu-pod -o wide || true; \
	$(K) describe pod pending-gpu-pod | tail -n 20 || true

case-3-revert:
	-$(K) delete -f manifests/case-3-pending.yaml --ignore-not-found

# ============================================================================
# Case 4: Multi-pod NCCL hang (bad MASTER_ADDR)
# Skill: hyperpod-nccl
# Prompt: "Multi-node NCCL training hangs at init, help"
# ============================================================================

case-4:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [eks case-4: NCCL hang]. CONFIRM=1 to apply."; \
	  exit 0; \
	fi; \
	set -e; \
	$(ensure_ns_inline) \
	echo "=== EKS case 4: NCCL job with broken MASTER_ADDR ==="; \
	$(K) apply -f manifests/case-4-nccl-hang.yaml; \
	sleep 10; \
	$(K) get pods -l app=nccl-hang -o wide || true

case-4-revert:
	-$(K) delete -f manifests/case-4-nccl-hang.yaml --ignore-not-found

# ============================================================================
# Case 5: Default-deny NetworkPolicy blocks pod-to-pod traffic
# Skill: hyperpod-nccl
# Prompt: "Pods can't reach each other, NCCL rendezvous fails"
# ============================================================================

case-5:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [eks case-5: NetworkPolicy block]. CONFIRM=1 to apply."; \
	  exit 0; \
	fi; \
	set -e; \
	$(ensure_ns_inline) \
	echo "=== EKS case 5: apply default-deny NetworkPolicy + 2-pod NCCL job ==="; \
	$(K) apply -f manifests/case-5-netpol.yaml; \
	sleep 10; \
	$(K) get pods,networkpolicy -l app=nccl-netpol || true

case-5-revert:
	-$(K) delete -f manifests/case-5-netpol.yaml --ignore-not-found
