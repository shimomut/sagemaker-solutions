#!/usr/bin/env bash
# Delete the periodic-audit CloudFormation stack.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-periodic-audit}"

if aws cloudformation describe-stacks --region "${REGION}" --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
    echo "==> Deleting stack ${STACK_NAME}"
    aws cloudformation delete-stack --region "${REGION}" --stack-name "${STACK_NAME}"
    aws cloudformation wait stack-delete-complete --region "${REGION}" --stack-name "${STACK_NAME}" || true
    echo "    deleted"
else
    echo "    stack not found; nothing to delete"
fi

if [[ -f "${STATE_FILE}" ]]; then
    python3 - "${STATE_FILE}" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    state = json.load(f)
state.pop("periodicAuditStackName", None)
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
PY
fi
echo "Done."
