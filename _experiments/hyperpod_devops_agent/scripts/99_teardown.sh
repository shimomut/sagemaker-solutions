#!/usr/bin/env bash
# Tears down everything created by 01/02/03 scripts, in reverse order.
# Safe to run repeatedly; each step ignores 'not found' errors.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

echo "==> Configuration"
print_config
echo

AGENT_SPACE_ID=""
AGENT_SPACE_ROLE_ARN=""
if [[ -f "${STATE_FILE}" ]]; then
    AGENT_SPACE_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('agentSpaceId',''))" "${STATE_FILE}" 2>/dev/null || true)"
    AGENT_SPACE_ROLE_ARN="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('agentSpaceRoleArn',''))" "${STATE_FILE}" 2>/dev/null || true)"
fi

# Fall back to constructing the role ARN from configured name if the state file
# is gone or stale.
if [[ -z "${AGENT_SPACE_ROLE_ARN}" ]]; then
    AGENT_SPACE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${AGENT_SPACE_ROLE_NAME}"
fi

echo "==> Step 1/4: Remove EKS access entry"
if aws eks describe-access-entry \
    --cluster-name "${EKS_CLUSTER_NAME}" \
    --region "${REGION}" \
    --principal-arn "${AGENT_SPACE_ROLE_ARN}" \
    >/dev/null 2>&1; then
    aws eks delete-access-entry \
        --cluster-name "${EKS_CLUSTER_NAME}" \
        --region "${REGION}" \
        --principal-arn "${AGENT_SPACE_ROLE_ARN}" \
        >/dev/null && echo "    deleted access entry"
else
    echo "    no access entry to delete"
fi

echo
echo "==> Step 2/4: Delete Agent Space"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    AGENT_SPACE_ID="$(aws devops-agent list-agent-spaces \
        --region "${REGION}" \
        --query "agentSpaces[?name=='${AGENT_SPACE_NAME}'].agentSpaceId | [0]" \
        --output text 2>/dev/null || true)"
fi
if [[ -n "${AGENT_SPACE_ID}" && "${AGENT_SPACE_ID}" != "None" ]]; then
    aws devops-agent delete-agent-space \
        --region "${REGION}" \
        --agent-space-id "${AGENT_SPACE_ID}" \
        >/dev/null && echo "    deleted agent space ${AGENT_SPACE_ID}"
else
    echo "    no agent space to delete"
fi

echo
echo "==> Step 3/4: Detach + delete IAM role ${AGENT_SPACE_ROLE_NAME}"
if aws iam get-role --role-name "${AGENT_SPACE_ROLE_NAME}" >/dev/null 2>&1; then
    aws iam delete-role-policy \
        --role-name "${AGENT_SPACE_ROLE_NAME}" \
        --policy-name AllowCreateServiceLinkedRoles >/dev/null 2>&1 || true
    aws iam detach-role-policy \
        --role-name "${AGENT_SPACE_ROLE_NAME}" \
        --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy >/dev/null 2>&1 || true
    aws iam delete-role --role-name "${AGENT_SPACE_ROLE_NAME}" && echo "    deleted ${AGENT_SPACE_ROLE_NAME}"
else
    echo "    role not found"
fi

echo
echo "==> Step 4/4: Detach + delete IAM role ${WEBAPP_ROLE_NAME}"
if aws iam get-role --role-name "${WEBAPP_ROLE_NAME}" >/dev/null 2>&1; then
    aws iam detach-role-policy \
        --role-name "${WEBAPP_ROLE_NAME}" \
        --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy >/dev/null 2>&1 || true
    aws iam delete-role --role-name "${WEBAPP_ROLE_NAME}" && echo "    deleted ${WEBAPP_ROLE_NAME}"
else
    echo "    role not found"
fi

rm -f "${STATE_FILE}" && echo "    removed ${STATE_FILE}"
echo
echo "Teardown complete."
