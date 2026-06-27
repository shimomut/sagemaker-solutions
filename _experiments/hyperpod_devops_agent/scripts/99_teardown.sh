#!/usr/bin/env bash
# Tears down everything created by 01/02/03 (and 05) scripts, in reverse order.
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

: "${STACK_NAME:=hyperpod-devops-agent-webhook-bridge}"
: "${EMAIL_STACK_NAME:=hyperpod-devops-agent-email-notifier}"

echo "==> Step 0a/3: Delete webhook bridge stack (if present)"
DELETE_SECRET="${DELETE_SECRET:-no}" STACK_NAME="${STACK_NAME}" \
    bash "${HERE}/06_delete_webhook_bridge.sh" || true
echo

echo "==> Step 0b/3: Delete email notifier stack (if present)"
if aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${EMAIL_STACK_NAME}" \
    >/dev/null 2>&1; then
    STACK_NAME="${EMAIL_STACK_NAME}" bash "${HERE}/11_delete_email_notifier.sh" || true
else
    echo "    no email notifier stack to delete"
fi
echo

echo "==> Step 1/3: Remove EKS access entry"
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

echo
echo "==> Step 2/3: Delete Agent Space (and disassociate + deregister eventChannel)"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    AGENT_SPACE_ID="$(aws devops-agent list-agent-spaces \
        --region "${REGION}" \
        --query "agentSpaces[?name=='${AGENT_SPACE_NAME}'].agentSpaceId | [0]" \
        --output text 2>/dev/null || true)"
fi
if [[ -n "${AGENT_SPACE_ID}" && "${AGENT_SPACE_ID}" != "None" ]]; then
    # Disassociate every non-AWS service association first (eventChannel etc).
    # delete-agent-space appears to be fine with these still attached, but
    # disassociating leaves the registered service usable for a future space.
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

    aws devops-agent delete-agent-space \
        --region "${REGION}" \
        --agent-space-id "${AGENT_SPACE_ID}" \
        >/dev/null && echo "    deleted agent space ${AGENT_SPACE_ID}"
else
    echo "    no agent space to delete"
fi

# Deregister any eventChannel services left behind in this account. We don't
# have a service id that's always reliable in state, so list filter on the
# service type.
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
echo "==> Step 3/3: Delete IAM roles CloudFormation stack"
: "${IAM_STACK_NAME:=hyperpod-devops-agent-iam-roles}"
if aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${IAM_STACK_NAME}" \
    >/dev/null 2>&1; then
    aws cloudformation delete-stack --region "${REGION}" --stack-name "${IAM_STACK_NAME}"
    aws cloudformation wait stack-delete-complete --region "${REGION}" --stack-name "${IAM_STACK_NAME}" || true
    echo "    deleted stack ${IAM_STACK_NAME}"
else
    echo "    IAM roles stack not found"
fi

rm -f "${STATE_FILE}" && echo "    removed ${STATE_FILE}"
echo
echo "Teardown complete."
