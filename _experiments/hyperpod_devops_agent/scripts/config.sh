#!/usr/bin/env bash
# Shared configuration for the DevOps Agent + HyperPod scripts.
# Customers MUST set HYPERPOD_CLUSTER_NAME before running. Other values
# have safe defaults or are auto-discovered.

set -euo pipefail

# AWS region for the Agent Space. Defaults to the AWS CLI's resolved region.
if [[ -z "${REGION:-}" ]]; then
    REGION="$(aws configure get region 2>/dev/null || echo "")"
fi
if [[ -z "${REGION}" ]]; then
    echo "Error: REGION not set and no default region in AWS config." >&2
    echo "  Export REGION=<region> or run 'aws configure set region <region>'." >&2
    exit 1
fi

# Resolved at runtime from the current caller identity unless set.
if [[ -z "${ACCOUNT_ID:-}" ]]; then
    ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

# Customer's HyperPod cluster name. No default — must be provided.
if [[ -z "${HYPERPOD_CLUSTER_NAME:-}" ]]; then
    echo "Error: HYPERPOD_CLUSTER_NAME is required." >&2
    echo "  Export HYPERPOD_CLUSTER_NAME=<your-cluster-name> before running." >&2
    exit 1
fi

# Underlying EKS cluster name. Auto-discovered from the HyperPod cluster's
# Orchestrator.Eks.ClusterArn when not set. Empty if the cluster is Slurm.
if [[ -z "${EKS_CLUSTER_NAME:-}" ]]; then
    EKS_ARN="$(aws sagemaker describe-cluster \
        --cluster-name "${HYPERPOD_CLUSTER_NAME}" \
        --region "${REGION}" \
        --query 'Orchestrator.Eks.ClusterArn' \
        --output text 2>/dev/null || echo "")"
    if [[ -n "${EKS_ARN}" && "${EKS_ARN}" != "None" ]]; then
        EKS_CLUSTER_NAME="${EKS_ARN##*/}"
    else
        EKS_CLUSTER_NAME=""
    fi
fi

# IAM role names.
: "${AGENT_SPACE_ROLE_NAME:=DevOpsAgentRole-AgentSpace}"
: "${WEBAPP_ROLE_NAME:=DevOpsAgentRole-WebappAdmin}"

# Agent Space friendly name. Sanitize cluster name for use in resource names.
SAFE_CLUSTER_NAME="$(echo "${HYPERPOD_CLUSTER_NAME}" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-')"
: "${AGENT_SPACE_NAME:=hyperpod-${SAFE_CLUSTER_NAME}-devops-agent}"
: "${AGENT_SPACE_DESCRIPTION:=AWS DevOps Agent monitoring HyperPod cluster ${HYPERPOD_CLUSTER_NAME}}"

# Local state file produced by setup steps so later steps can find the agent space id.
STATE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.state.json"

export REGION ACCOUNT_ID HYPERPOD_CLUSTER_NAME EKS_CLUSTER_NAME
export AGENT_SPACE_ROLE_NAME WEBAPP_ROLE_NAME
export AGENT_SPACE_NAME AGENT_SPACE_DESCRIPTION STATE_FILE

print_config() {
    echo "Region:           ${REGION}"
    echo "Account:          ${ACCOUNT_ID}"
    echo "HyperPod cluster: ${HYPERPOD_CLUSTER_NAME}"
    echo "EKS cluster:      ${EKS_CLUSTER_NAME:-<none — Slurm or undiscovered>}"
    echo "Agent Space role: ${AGENT_SPACE_ROLE_NAME}"
    echo "Webapp role:      ${WEBAPP_ROLE_NAME}"
    echo "Agent Space name: ${AGENT_SPACE_NAME}"
    echo "State file:       ${STATE_FILE}"
}
