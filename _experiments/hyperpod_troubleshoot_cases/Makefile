SHELL := /bin/bash

# Top-level dispatcher. Forwards to slurm/Makefile or eks/Makefile.
#
# Usage:
#   make list
#   make slurm-case-1                  # dry-run by default
#   make slurm-case-1 CONFIRM=1        # actually break something
#   make slurm-case-1-revert
#   make eks-case-2 CONFIRM=1
#
# Common variables:
#   CONFIRM=1                          # required for any destructive trigger
#   HP_CLUSTER_NAME=<name>             # HyperPod cluster name (for SSM)
#   NODE=<instance-id-or-slurm-node>   # target a specific node
#   GPU=<index>                        # GPU index (default 0)

CONFIRM ?= 0
HP_CLUSTER_NAME ?=
NODE ?=
GPU ?= 0

EXPORTS = CONFIRM=$(CONFIRM) HP_CLUSTER_NAME=$(HP_CLUSTER_NAME) NODE=$(NODE) GPU=$(GPU)

.PHONY: help list sanity-check
.PHONY: slurm-case-1 slurm-case-1-revert
.PHONY: slurm-case-2 slurm-case-2-revert
.PHONY: slurm-case-3 slurm-case-3-revert
.PHONY: slurm-case-4 slurm-case-4-revert
.PHONY: slurm-case-5 slurm-case-5-revert
.PHONY: eks-case-1 eks-case-1-revert
.PHONY: eks-case-2 eks-case-2-revert
.PHONY: eks-case-3 eks-case-3-revert
.PHONY: eks-case-4 eks-case-4-revert
.PHONY: eks-case-5 eks-case-5-revert

help: list

list:
	@echo "HyperPod Troubleshoot Cases"
	@echo ""
	@echo "Slurm:"
	@echo "  slurm-case-1   node-drain              (hyperpod-slurm-debugger)"
	@echo "  slurm-case-2   stuck-pending           (hyperpod-slurm-debugger)"
	@echo "  slurm-case-3   gpu-xid-inject          (hyperpod-node-debugger)        [CONFIRM=1]"
	@echo "  slurm-case-4   disk-pressure           (hyperpod-node-debugger)        [CONFIRM=1]"
	@echo "  slurm-case-5   nccl-hang               (hyperpod-nccl)"
	@echo ""
	@echo "EKS:"
	@echo "  eks-case-1     pod-oom                 (hyperpod-nccl)"
	@echo "  eks-case-2     crashloopbackoff        (hyperpod-nccl)"
	@echo "  eks-case-3     pending-unschedulable   (hyperpod-nccl)"
	@echo "  eks-case-4     nccl-hang               (hyperpod-nccl)"
	@echo "  eks-case-5     networkpolicy-block     (hyperpod-nccl)"
	@echo ""
	@echo "Each case has a -revert counterpart. Pass CONFIRM=1 to actually trigger."

sanity-check:
	@if [ "$(ORCH)" = "slurm" ]; then $(MAKE) -C slurm sanity-check; \
	elif [ "$(ORCH)" = "eks" ]; then $(MAKE) -C eks sanity-check; \
	else echo "Usage: make sanity-check ORCH=slurm|eks"; exit 1; fi

# --- Slurm dispatch ---------------------------------------------------------

slurm-case-1:        ; @$(EXPORTS) $(MAKE) -C slurm case-1
slurm-case-1-revert: ; @$(EXPORTS) $(MAKE) -C slurm case-1-revert
slurm-case-2:        ; @$(EXPORTS) $(MAKE) -C slurm case-2
slurm-case-2-revert: ; @$(EXPORTS) $(MAKE) -C slurm case-2-revert
slurm-case-3:        ; @$(EXPORTS) $(MAKE) -C slurm case-3
slurm-case-3-revert: ; @$(EXPORTS) $(MAKE) -C slurm case-3-revert
slurm-case-4:        ; @$(EXPORTS) $(MAKE) -C slurm case-4
slurm-case-4-revert: ; @$(EXPORTS) $(MAKE) -C slurm case-4-revert
slurm-case-5:        ; @$(EXPORTS) $(MAKE) -C slurm case-5
slurm-case-5-revert: ; @$(EXPORTS) $(MAKE) -C slurm case-5-revert

# --- EKS dispatch -----------------------------------------------------------

eks-case-1:        ; @$(EXPORTS) $(MAKE) -C eks case-1
eks-case-1-revert: ; @$(EXPORTS) $(MAKE) -C eks case-1-revert
eks-case-2:        ; @$(EXPORTS) $(MAKE) -C eks case-2
eks-case-2-revert: ; @$(EXPORTS) $(MAKE) -C eks case-2-revert
eks-case-3:        ; @$(EXPORTS) $(MAKE) -C eks case-3
eks-case-3-revert: ; @$(EXPORTS) $(MAKE) -C eks case-3-revert
eks-case-4:        ; @$(EXPORTS) $(MAKE) -C eks case-4
eks-case-4-revert: ; @$(EXPORTS) $(MAKE) -C eks case-4-revert
eks-case-5:        ; @$(EXPORTS) $(MAKE) -C eks case-5
eks-case-5-revert: ; @$(EXPORTS) $(MAKE) -C eks case-5-revert
