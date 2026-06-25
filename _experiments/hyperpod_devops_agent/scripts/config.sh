#!/usr/bin/env bash
# Shared configuration for the DevOps Agent + HyperPod PoC scripts.
# Override any of these by exporting them before running the make targets.

set -euo pipefail

# AWS region for the Agent Space. Cluster k8-1 is in us-west-2.
: "${REGION:=us-west-2}"

# Resolved at runtime from the current caller identity unless set.
if [[ -z "${ACCOUNT_ID:-}" ]]; then
    ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

# HyperPod cluster + its underlying EKS cluster name.
: "${HYPERPOD_CLUSTER_NAME:=k8-1}"
: "${EKS_CLUSTER_NAME:=sagemaker-k8-1-1bd2626f-eks}"

# IAM role names.
: "${AGENT_SPACE_ROLE_NAME:=DevOpsAgentRole-AgentSpace}"
: "${WEBAPP_ROLE_NAME:=DevOpsAgentRole-WebappAdmin}"

# Agent Space friendly name.
: "${AGENT_SPACE_NAME:=hyperpod-devops-agent-poc}"
: "${AGENT_SPACE_DESCRIPTION:=PoC: AWS DevOps Agent monitoring HyperPod cluster ${HYPERPOD_CLUSTER_NAME}}"

# Local state file produced by setup steps so later steps can find the agent space id.
STATE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.state.json"

export REGION ACCOUNT_ID HYPERPOD_CLUSTER_NAME EKS_CLUSTER_NAME
export AGENT_SPACE_ROLE_NAME WEBAPP_ROLE_NAME
export AGENT_SPACE_NAME AGENT_SPACE_DESCRIPTION STATE_FILE

print_config() {
    echo "Region:           ${REGION}"
    echo "Account:          ${ACCOUNT_ID}"
    echo "HyperPod cluster: ${HYPERPOD_CLUSTER_NAME}"
    echo "EKS cluster:      ${EKS_CLUSTER_NAME}"
    echo "Agent Space role: ${AGENT_SPACE_ROLE_NAME}"
    echo "Webapp role:      ${WEBAPP_ROLE_NAME}"
    echo "Agent Space name: ${AGENT_SPACE_NAME}"
    echo "State file:       ${STATE_FILE}"
}
