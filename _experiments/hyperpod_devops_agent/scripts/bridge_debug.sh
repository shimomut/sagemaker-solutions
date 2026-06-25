#!/usr/bin/env bash
# Toggle debug logging on the deployed webhook bridge Lambda WITHOUT redeploying
# the CloudFormation stack. Useful for inspecting the exact JSON body the Lambda
# sends to the DevOps Agent webhook.
#
# Usage:
#   bash bridge_debug.sh on              # full event + outgoing payload logging
#   bash bridge_debug.sh on yes          # same, plus DRY_RUN (skip the POST)
#   bash bridge_debug.sh off             # restore normal logging
#
# All other env vars on the Lambda (WEBHOOK_SECRET_ARN, WEBHOOK_DROP_EVENT_LEVELS)
# are preserved.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

MODE="${1:-on}"
DRY_RUN="${2:-no}"

FUNC="$(aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name hyperpod-devops-agent-webhook-bridge \
    --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue | [0]" \
    --output text)"

if [[ -z "${FUNC}" || "${FUNC}" == "None" ]]; then
    echo "Error: webhook bridge stack not deployed." >&2
    exit 1
fi

# Fetch the current Variables map so we can patch it in place.
CURRENT="$(aws lambda get-function-configuration \
    --region "${REGION}" \
    --function-name "${FUNC}" \
    --query 'Environment.Variables' \
    --output json)"

NEW_VARS="$(python3 - "${CURRENT}" "${MODE}" "${DRY_RUN}" <<'PY'
import json, sys
current, mode, dry_run = sys.argv[1:]
vars = json.loads(current)
debug_keys = ["WEBHOOK_LOG_FULL_EVENT", "WEBHOOK_LOG_PAYLOAD", "WEBHOOK_DRY_RUN"]
for k in debug_keys:
    vars.pop(k, None)
if mode == "on":
    vars["WEBHOOK_LOG_FULL_EVENT"] = "true"
    vars["WEBHOOK_LOG_PAYLOAD"] = "true"
    if dry_run.lower() in {"1", "true", "yes", "on"}:
        vars["WEBHOOK_DRY_RUN"] = "true"
print(json.dumps({"Variables": vars}))
PY
)"

echo "==> Updating Lambda ${FUNC} env"
echo "${NEW_VARS}" | python3 -m json.tool

aws lambda update-function-configuration \
    --region "${REGION}" \
    --function-name "${FUNC}" \
    --environment "${NEW_VARS}" \
    --query 'Environment.Variables' \
    --output table

echo
echo "Done. Now: 'make bridge-logs' to tail, then fire an event."
