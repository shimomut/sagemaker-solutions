#!/usr/bin/env bash
# Tears down everything created by 01/02/03/05/10, in reverse order.
# Safe to run repeatedly; each step ignores 'not found' errors.
#
# The webhook secret in Secrets Manager is left in place by default; pass
# DELETE_SECRET=yes to also remove it.

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

: "${BRIDGE_STACK_NAME:=hyperpod-devops-agent-webhook-bridge}"
: "${EMAIL_STACK_NAME:=hyperpod-devops-agent-email-notifier}"
: "${FOUNDATION_STACK_NAME:=hyperpod-devops-agent-foundation}"

echo "==> Step 0a/4: Delete webhook bridge stack (if present)"
DELETE_SECRET="${DELETE_SECRET:-no}" STACK_NAME="${BRIDGE_STACK_NAME}" \
    bash "${HERE}/06_delete_webhook_bridge.sh" || true
echo

echo "==> Step 0b/4: Delete email notifier stack (if present)"
if aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${EMAIL_STACK_NAME}" \
    >/dev/null 2>&1; then
    STACK_NAME="${EMAIL_STACK_NAME}" bash "${HERE}/11_delete_email_notifier.sh" || true
else
    echo "    no email notifier stack to delete"
fi
echo

echo "==> Step 0c/4: Delete periodic-audit stack (if present)"
bash "${HERE}/13_delete_periodic_audit.sh" || true
echo

echo "==> Step 1/4: Remove EKS access entry"
if [[ -z "${EKS_CLUSTER_NAME:-}" ]]; then
    echo "    no EKS cluster associated; nothing to remove"
elif aws eks describe-access-entry \
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

# eventChannel webhook lives outside the foundation CFN stack. It MUST be
# disassociated before CFN can delete the AgentSpace, because CFN-managed
# AgentSpace deletion will fail if "extra" associations are attached.
echo
echo "==> Step 2/4: Disassociate + deregister eventChannel webhook (outside CFN)"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    AGENT_SPACE_ID="$(aws devops-agent list-agent-spaces \
        --region "${REGION}" \
        --query "agentSpaces[?name=='${AGENT_SPACE_NAME}'].agentSpaceId | [0]" \
        --output text 2>/dev/null || true)"
fi
if [[ -n "${AGENT_SPACE_ID}" && "${AGENT_SPACE_ID}" != "None" ]]; then
    EVENT_CHANNEL_ASSOC_IDS="$(aws devops-agent list-associations \
        --region "${REGION}" \
        --agent-space-id "${AGENT_SPACE_ID}" \
        --query "associations[?configuration.eventChannel!=null].associationId" \
        --output text 2>/dev/null || true)"
    for ASSOC_ID in ${EVENT_CHANNEL_ASSOC_IDS}; do
        aws devops-agent disassociate-service \
            --region "${REGION}" \
            --agent-space-id "${AGENT_SPACE_ID}" \
            --association-id "${ASSOC_ID}" \
            >/dev/null 2>&1 && echo "    disassociated eventChannel association ${ASSOC_ID}" || true
    done
else
    echo "    no agent space found; skipping"
fi

# Deregister any eventChannel services left behind in this account.
EVENT_CHANNEL_SVC_IDS="$(aws devops-agent list-services \
    --region "${REGION}" \
    --query "services[?serviceType=='eventChannel' || serviceTypeName=='eventChannel'].serviceId" \
    --output text 2>/dev/null || true)"
for SVC_ID in ${EVENT_CHANNEL_SVC_IDS}; do
    aws devops-agent deregister-service \
        --region "${REGION}" \
        --service-id "${SVC_ID}" \
        >/dev/null 2>&1 && echo "    deregistered eventChannel service ${SVC_ID}" || true
done

echo
echo "==> Step 3/4: Delete foundation CloudFormation stack (IAM roles + AgentSpace + AWS association)"
if aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${FOUNDATION_STACK_NAME}" \
    >/dev/null 2>&1; then
    aws cloudformation delete-stack --region "${REGION}" --stack-name "${FOUNDATION_STACK_NAME}"
    aws cloudformation wait stack-delete-complete --region "${REGION}" --stack-name "${FOUNDATION_STACK_NAME}" || true
    echo "    deleted stack ${FOUNDATION_STACK_NAME}"
else
    echo "    foundation stack not found"
fi

echo
echo "==> Step 4/4: Cleanup state file"
rm -f "${STATE_FILE}" && echo "    removed ${STATE_FILE}"
echo
echo "Teardown complete."
