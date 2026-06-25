#!/usr/bin/env bash
# Embeds lambda_function.py into the CloudFormation template and deploys (or
# updates) the webhook bridge stack.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-webhook-bridge}"
TEMPLATE_SRC="${ROOT}/webhook_bridge/template.yaml"
TEMPLATE_OUT="${ROOT}/webhook_bridge/template.embedded.yaml"
LAMBDA_SRC="${ROOT}/webhook_bridge/lambda_function.py"

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make webhook-secret' first." >&2
    exit 1
fi

WEBHOOK_SECRET_ARN="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('webhookSecretArn',''))" "${STATE_FILE}")"
if [[ -z "${WEBHOOK_SECRET_ARN}" ]]; then
    echo "Error: webhookSecretArn missing from ${STATE_FILE}. Run 'make webhook-secret' first." >&2
    exit 1
fi

echo "==> Configuration"
print_config
echo "Stack name:         ${STACK_NAME}"
echo "Webhook secret ARN: ${WEBHOOK_SECRET_ARN}"
echo

echo "==> Embedding Lambda code into template"
awk '/# LAMBDA_CODE_PLACEHOLDER/ {
    while ((getline line < "'"${LAMBDA_SRC}"'") > 0) {
        if (line == "") { print "" }
        else { print "          " line }
    }
    close("'"${LAMBDA_SRC}"'")
    next
}
{ print }' "${TEMPLATE_SRC}" > "${TEMPLATE_OUT}"
echo "    wrote ${TEMPLATE_OUT}"

echo
echo "==> Deploying stack ${STACK_NAME}"
aws cloudformation deploy \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --template-file "${TEMPLATE_OUT}" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides "WebhookSecretArn=${WEBHOOK_SECRET_ARN}"

echo
echo "==> Stack outputs"
aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

python3 - "${STATE_FILE}" "${STACK_NAME}" <<'PY'
import json, sys
path, stack_name = sys.argv[1:]
with open(path) as f:
    state = json.load(f)
state["webhookBridgeStackName"] = stack_name
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
PY
