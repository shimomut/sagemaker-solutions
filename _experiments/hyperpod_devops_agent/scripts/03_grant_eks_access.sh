#!/usr/bin/env bash
# Grants the Agent Space monitoring role read-only access to the HyperPod
# underlying EKS cluster by creating an EKS access entry and associating the
# AWS-managed AmazonAIOpsAssistantPolicy access policy (cluster scope).
#
# Prerequisite: the EKS cluster's authentication mode must include the EKS API
# (API or API_AND_CONFIG_MAP). The script verifies this and aborts if the
# cluster is on CONFIG_MAP-only.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make iam-roles' and 'make agent-space' first." >&2
    exit 1
fi

AGENT_SPACE_ROLE_ARN="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['agentSpaceRoleArn'])" "${STATE_FILE}")"

echo "==> Configuration"
print_config
echo "Agent Space role ARN: ${AGENT_SPACE_ROLE_ARN}"
echo

echo "==> Step 1/2: Verify EKS cluster auth mode includes the EKS API"
AUTH_MODE="$(aws eks describe-cluster \
    --name "${EKS_CLUSTER_NAME}" \
    --region "${REGION}" \
    --query 'cluster.accessConfig.authenticationMode' \
    --output text)"
echo "    authenticationMode = ${AUTH_MODE}"
if [[ "${AUTH_MODE}" != "API" && "${AUTH_MODE}" != "API_AND_CONFIG_MAP" ]]; then
    echo "Error: EKS cluster '${EKS_CLUSTER_NAME}' has authenticationMode=${AUTH_MODE}."
    echo "  DevOps Agent EKS access requires API or API_AND_CONFIG_MAP."
    echo "  Update with: aws eks update-cluster-config --name ${EKS_CLUSTER_NAME} --region ${REGION} \\"
    echo "                  --access-config authenticationMode=API_AND_CONFIG_MAP"
    exit 1
fi

echo
echo "==> Step 2/2: Create EKS access entry + associate AmazonAIOpsAssistantPolicy"
if aws eks describe-access-entry \
    --cluster-name "${EKS_CLUSTER_NAME}" \
    --region "${REGION}" \
    --principal-arn "${AGENT_SPACE_ROLE_ARN}" \
    >/dev/null 2>&1; then
    echo "    access entry for ${AGENT_SPACE_ROLE_ARN} already exists"
else
    echo "    creating access entry for ${AGENT_SPACE_ROLE_ARN}"
    aws eks create-access-entry \
        --cluster-name "${EKS_CLUSTER_NAME}" \
        --region "${REGION}" \
        --principal-arn "${AGENT_SPACE_ROLE_ARN}" \
        --type STANDARD \
        >/dev/null
fi

aws eks associate-access-policy \
    --cluster-name "${EKS_CLUSTER_NAME}" \
    --region "${REGION}" \
    --principal-arn "${AGENT_SPACE_ROLE_ARN}" \
    --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonAIOpsAssistantPolicy \
    --access-scope type=cluster \
    >/dev/null
echo "    AmazonAIOpsAssistantPolicy associated (cluster scope)"

echo
echo "Done. The Agent Space monitoring role now has read-only access to ${EKS_CLUSTER_NAME}."
