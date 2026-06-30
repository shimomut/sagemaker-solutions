#!/usr/bin/env bash
# Deploy the periodic-audit stack: Lambda + EventBridge Scheduler.
#
# This is the fallback for Goal 1 (monitor incident duration + Resolved
# closure notification). DevOps Agent's native scheduled triggers fire,
# but they create CUSTOM tasks with no AWS API executor and a different
# skill-mount path than investigations — they can't actually run the
# hyperpod-incident skill. The EB Scheduler + Lambda pattern POSTs a
# synthetic event directly to the same webhook the bridge uses, so the
# audit goes through the working investigation path.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-periodic-audit}"
: "${SCHEDULE:=rate(15 minutes)}"

TEMPLATE_SRC="${ROOT}/periodic_audit/template.yaml"
TEMPLATE_OUT="${ROOT}/periodic_audit/template.embedded.yaml"
LAMBDA_SRC="${ROOT}/periodic_audit/lambda_function.py"

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make foundation' first." >&2
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
echo "Schedule:           ${SCHEDULE}"
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
    --parameter-overrides \
        "WebhookSecretArn=${WEBHOOK_SECRET_ARN}" \
        "ClusterName=${HYPERPOD_CLUSTER_NAME}" \
        "Schedule=${SCHEDULE}"

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
state["periodicAuditStackName"] = stack_name
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
PY

echo
echo "Done. Audit will fire ${SCHEDULE}."
echo "Tail the audit Lambda logs with:"
echo "  make audit-logs"
