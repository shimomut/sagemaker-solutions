#!/usr/bin/env bash
# Deletes the webhook bridge CloudFormation stack and (optionally) the
# Secrets Manager secret. Run AFTER 'make teardown' if you want to wipe
# the bridge separately, or before 'make teardown' as part of a full
# cleanup.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-webhook-bridge}"
: "${SECRET_NAME:=hyperpod-devops-agent/webhook}"

echo "==> Configuration"
print_config
echo "Stack name:  ${STACK_NAME}"
echo "Secret name: ${SECRET_NAME}"
echo

echo "==> Deleting stack ${STACK_NAME}"
if aws cloudformation describe-stacks --region "${REGION}" --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
    aws cloudformation delete-stack --region "${REGION}" --stack-name "${STACK_NAME}"
    echo "    delete requested; waiting for completion..."
    aws cloudformation wait stack-delete-complete --region "${REGION}" --stack-name "${STACK_NAME}" || true
    echo "    stack deleted"
else
    echo "    stack not found"
fi

if [[ "${DELETE_SECRET:-no}" == "yes" ]]; then
    echo
    echo "==> Deleting Secrets Manager secret ${SECRET_NAME} (force, no recovery window)"
    if aws secretsmanager describe-secret --region "${REGION}" --secret-id "${SECRET_NAME}" >/dev/null 2>&1; then
        aws secretsmanager delete-secret \
            --region "${REGION}" \
            --secret-id "${SECRET_NAME}" \
            --force-delete-without-recovery >/dev/null
        echo "    secret deleted"
    else
        echo "    secret not found"
    fi
else
    echo
    echo "Note: webhook secret left in place. Re-run with DELETE_SECRET=yes to remove it."
fi
