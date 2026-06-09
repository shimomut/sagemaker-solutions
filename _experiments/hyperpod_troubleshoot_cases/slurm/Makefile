SHELL := /bin/bash

# Slurm-side troubleshooting cases. Run from a HyperPod head/login node.
#
# Variables:
#   CONFIRM=1            actually run the destructive trigger (default: dry-run)
#   NODE=<slurm-name>    Slurm node to target (default: first idle compute)
#   HP_CLUSTER_NAME      HyperPod cluster name (only needed for SSM cases)
#   GPU=<index>          GPU index (default 0)

CONFIRM ?= 0
NODE ?=
GPU ?= 0
HP_CLUSTER_NAME ?=

OUTPUT_DIR := output

.PHONY: sanity-check
.PHONY: case-1 case-1-revert
.PHONY: case-2 case-2-revert
.PHONY: case-3 case-3-revert
.PHONY: case-4 case-4-revert
.PHONY: case-5 case-5-revert

sanity-check:
	@echo "=== Slurm sanity check ==="
	@which sinfo scontrol sbatch >/dev/null || { echo "Slurm CLI not found"; exit 1; }
	@sinfo
	@echo ""
	@echo "Cluster name (from instance user-data): $$(ec2-metadata --user-data 2>/dev/null | grep -oE 'CLUSTER_NAME=[^ ]+' || echo unknown)"

# Each case body is a single shell invocation so the CONFIRM gate's `exit 0`
# actually short-circuits the destructive commands.

# ============================================================================
# Case 1: Slurm node stuck in DRAIN state
# Skill: hyperpod-slurm-debugger
# Prompt: "A Slurm node is stuck in drain state, diagnose it"
# ============================================================================

case-1:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [slurm case-1: drain node]. CONFIRM=1 to drain."; \
	  exit 0; \
	fi; \
	set -e; \
	target="$(NODE)"; \
	if [ -z "$$target" ]; then target=$$(sinfo -h -t idle -o '%n' | head -n1); fi; \
	if [ -z "$$target" ]; then echo "no idle node available; pass NODE=<name>"; exit 1; fi; \
	echo "=== draining $$target ==="; \
	sudo scontrol update nodename=$$target state=drain reason="hp_troubleshoot_cases:case-1"; \
	sinfo -h -n $$target -o '%n %t %E'

case-1-revert:
	@set -e; \
	target="$(NODE)"; \
	if [ -z "$$target" ]; then echo "specify NODE=<name>"; exit 1; fi; \
	sudo scontrol update nodename=$$target state=undrain || true; \
	sudo scontrol update nodename=$$target state=resume || true; \
	sinfo -h -n $$target -o '%n %t %E'

# ============================================================================
# Case 2: Job stuck PENDING with REASON=Resources
# Skill: hyperpod-slurm-debugger
# Prompt: "Slurm job is stuck PENDING with REASON=Resources, why?"
# ============================================================================

case-2:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [slurm case-2: oversubscribed job]. CONFIRM=1 to submit."; \
	  exit 0; \
	fi; \
	set -e; \
	mkdir -p $(OUTPUT_DIR); \
	total=$$(sinfo -h -o '%D' | awk '{s+=$$1} END {print s}'); \
	oversize=$$((total + 10)); \
	echo "submitting job that requests $$oversize nodes (cluster has $$total)..."; \
	sed "s/__NODES__/$$oversize/g" jobs/oversubscribed.sbatch > $(OUTPUT_DIR)/oversubscribed.sbatch; \
	jobid=$$(sbatch --parsable $(OUTPUT_DIR)/oversubscribed.sbatch); \
	echo "$$jobid" > $(OUTPUT_DIR)/case-2.jobid; \
	echo "submitted job $$jobid"; \
	sleep 2; \
	squeue -j $$jobid

case-2-revert:
	@if [ -f $(OUTPUT_DIR)/case-2.jobid ]; then \
	  jobid=$$(cat $(OUTPUT_DIR)/case-2.jobid); \
	  scancel $$jobid && echo "cancelled job $$jobid"; \
	  rm -f $(OUTPUT_DIR)/case-2.jobid; \
	else echo "no job recorded"; fi

# ============================================================================
# Case 3: GPU XID injection on a worker node (DCGM)
# Skill: hyperpod-node-debugger
# Prompt: "GPU on node X is reporting hardware errors, investigate"
# ============================================================================

case-3:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [slurm case-3: inject XID 94]. CONFIRM=1 to inject."; \
	  exit 0; \
	fi; \
	set -e; \
	target="$(NODE)"; \
	if [ -z "$$target" ]; then target=$$(sinfo -h -t idle -o '%n' | head -n1); fi; \
	if [ -z "$$target" ]; then echo "no idle node available; pass NODE=<name>"; exit 1; fi; \
	echo "=== injecting XID 94 on $$target GPU $(GPU) ==="; \
	ssh -o StrictHostKeyChecking=no $$target "sudo dcgmi test --inject --gpuid $(GPU) -f 230 -v 94"; \
	echo "DCGM health on $$target:"; \
	ssh -o StrictHostKeyChecking=no $$target 'dcgmi health -g 0 -c' || true

case-3-revert:
	@set -e; \
	target="$(NODE)"; \
	if [ -z "$$target" ]; then echo "specify NODE=<name>"; exit 1; fi; \
	ssh -o StrictHostKeyChecking=no $$target 'sudo systemctl restart nvidia-dcgm 2>/dev/null || sudo systemctl restart dcgm' || true; \
	echo "DCGM restarted on $$target; injected values cleared."

# ============================================================================
# Case 4: Disk pressure on a worker node
# Skill: hyperpod-node-debugger
# Prompt: "A worker node is unresponsive, check it"
# ============================================================================

case-4:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [slurm case-4: fill disk]. CONFIRM=1 to fill disk."; \
	  exit 0; \
	fi; \
	set -e; \
	target="$(NODE)"; \
	if [ -z "$$target" ]; then target=$$(sinfo -h -t idle -o '%n' | head -n1); fi; \
	if [ -z "$$target" ]; then echo "no idle node available; pass NODE=<name>"; exit 1; fi; \
	echo "=== filling /var/log on $$target to 95% ==="; \
	scp -o StrictHostKeyChecking=no scripts/fill-disk.sh $$target:/tmp/fill-disk.sh; \
	ssh -o StrictHostKeyChecking=no $$target 'sudo bash /tmp/fill-disk.sh --target 95'

case-4-revert:
	@set -e; \
	target="$(NODE)"; \
	if [ -z "$$target" ]; then echo "specify NODE=<name>"; exit 1; fi; \
	ssh -o StrictHostKeyChecking=no $$target 'sudo bash /tmp/fill-disk.sh --cleanup' || true

# ============================================================================
# Case 5: NCCL hang from mismatched world-size
# Skill: hyperpod-nccl
# Prompt: "Training job hangs at NCCL AllReduce, help me debug"
# ============================================================================

case-5:
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "DRY RUN [slurm case-5: NCCL hang job]. CONFIRM=1 to submit."; \
	  exit 0; \
	fi; \
	set -e; \
	mkdir -p $(OUTPUT_DIR); \
	count=$$(sinfo -h -t idle -o '%D' | awk '{s+=$$1} END {print s}'); \
	if [ "$$count" -lt 2 ]; then echo "need at least 2 idle nodes (have $$count)"; exit 1; fi; \
	jobid=$$(sbatch --parsable jobs/nccl-hang.sbatch); \
	echo "$$jobid" > $(OUTPUT_DIR)/case-5.jobid; \
	echo "submitted NCCL hang job $$jobid (will hang ~10 min then time out)."

case-5-revert:
	@if [ -f $(OUTPUT_DIR)/case-5.jobid ]; then \
	  jobid=$$(cat $(OUTPUT_DIR)/case-5.jobid); \
	  scancel $$jobid && echo "cancelled $$jobid"; \
	  rm -f $(OUTPUT_DIR)/case-5.jobid; \
	else echo "no job recorded"; fi
