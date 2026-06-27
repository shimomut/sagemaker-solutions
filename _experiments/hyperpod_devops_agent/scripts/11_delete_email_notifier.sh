#!/usr/bin/env bash
# Delete the email notifier CloudFormation stack.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-email-notifier}"

echo "==> Deleting stack ${STACK_NAME}"
aws cloudformation delete-stack --region "${REGION}" --stack-name "${STACK_NAME}"
aws cloudformation wait stack-delete-complete --region "${REGION}" --stack-name "${STACK_NAME}" || true

if [[ -f "${STATE_FILE}" ]]; then
    python3 - "${STATE_FILE}" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    state = json.load(f)
state.pop("emailNotifierStackName", None)
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
PY
fi

echo "Done."
