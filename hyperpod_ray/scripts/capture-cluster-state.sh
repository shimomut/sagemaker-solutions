#!/usr/bin/env bash
#
# Snapshot the parts of a HyperPod EKS cluster that a Ray setup step can change.
#
# Run it once before a console action and once after, then diff the two files.
# That turns "I clicked Install and something happened" into a reviewable list of
# what the console actually created.
#
# Usage:
#   bash scripts/capture-cluster-state.sh <hyperpod-cluster-name> <label>
#
# Example:
#   bash scripts/capture-cluster-state.sh k8-ray-3 before
#   # ... click Install in the console ...
#   bash scripts/capture-cluster-state.sh k8-ray-3 after
#   diff -u /tmp/hp-state-k8-ray-3-before.txt /tmp/hp-state-k8-ray-3-after.txt
#
# Read-only: every call is a describe/list/get. Nothing here mutates the cluster.

set -uo pipefail

CLUSTER="${1:?usage: capture-cluster-state.sh <hyperpod-cluster-name> <label>}"
LABEL="${2:?usage: capture-cluster-state.sh <hyperpod-cluster-name> <label>}"
REGION="${AWS_REGION:-us-west-2}"
OUT="${OUT:-/tmp/hp-state-${CLUSTER}-${LABEL}.txt}"

# Resolve the EKS cluster behind the HyperPod cluster so the caller only has to
# know the HyperPod name.
EKS_ARN=$(aws sagemaker describe-cluster --cluster-name "$CLUSTER" --region "$REGION" \
  --query 'Orchestrator.Eks.ClusterArn' --output text)
EKS_NAME="${EKS_ARN##*/}"

section() { printf '\n===== %s =====\n' "$1"; }

{
  echo "cluster: $CLUSTER"
  echo "eks: $EKS_NAME"
  echo "region: $REGION"
  # Deliberately no timestamp: it would show up in every diff as noise.

  section "helm releases"
  # The console's Ray install is a helm wrapper, so a new release here is the
  # primary evidence of what it did.
  helm list -A 2>&1

  section "ray crds"
  kubectl get crds -o name 2>&1 | grep -i ray || echo "(none)"

  section "namespaces"
  kubectl get ns -o name 2>&1 | sort

  section "eks addons"
  aws eks list-addons --cluster-name "$EKS_NAME" --region "$REGION" \
    --query 'addons' --output text 2>&1 | tr '\t' '\n' | sort

  section "eks access entries"
  # Granting a SageMaker domain access to the cluster creates one of these, so
  # this is how you see that step land without reading the console back.
  aws eks list-access-entries --cluster-name "$EKS_NAME" --region "$REGION" \
    --query 'accessEntries' --output text 2>&1 | tr '\t' '\n' | sort

  section "workloads outside kube-system"
  kubectl get deployments,statefulsets,daemonsets -A \
    --no-headers 2>&1 | grep -v '^kube-system' | awk '{print $1, $2}' | sort

  section "ray resources"
  kubectl get rayclusters,rayjobs,rayservices -A 2>&1 | head -20

  section "nodes"
  kubectl get nodes \
    -o custom-columns='NAME:.metadata.name,CPU:.status.allocatable.cpu,MEM:.status.allocatable.memory,IMAGE:.status.nodeInfo.osImage' \
    2>&1
} > "$OUT"

echo "wrote $OUT"
