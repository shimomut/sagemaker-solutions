#!/usr/bin/env bash
# Deploy the email notifier stack: EventBridge rule on aws.aidevops
# investigation events -> Lambda -> SES.
#
# Required env:
#   EMAIL_SENDER       SES-verified From address (in REGION)
#   EMAIL_RECIPIENTS   Comma-separated To addresses
#
# Optional env:
#   STACK_NAME              Override the CFN stack name
#   EMAIL_DETAIL_TYPES      Override which lifecycle events trigger emails
#                            (default: "Investigation Completed" — one email per investigation)
#   FORCE_SEND              "true" to bypass all filters including the dedup marker
#                            (default: "false"; useful for debugging)
#   MARKER_EXPIRATION_DAYS  How many days to retain per-execution email markers
#                            in the dedup S3 bucket (default: 30)
#   CONSOLE_URL_TEMPLATE    Override the URL template in the email body

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-email-notifier}"
: "${EMAIL_DETAIL_TYPES:=Investigation Completed}"
: "${CONSOLE_URL_TEMPLATE:=https://%agent_space_id%.aidevops.global.app.aws/investigation/%task_id%}"
: "${FORCE_SEND:=false}"
: "${MARKER_EXPIRATION_DAYS:=30}"

TEMPLATE_SRC="${ROOT}/email_notifier/template.yaml"
TEMPLATE_OUT="${ROOT}/email_notifier/template.embedded.yaml"
LAMBDA_SRC="${ROOT}/email_notifier/lambda_function.py"

if [[ -z "${EMAIL_SENDER:-}" ]]; then
    echo "Error: EMAIL_SENDER is required (must be a verified SES identity in ${REGION})." >&2
    exit 1
fi
if [[ -z "${EMAIL_RECIPIENTS:-}" ]]; then
    echo "Error: EMAIL_RECIPIENTS is required (comma-separated To addresses)." >&2
    exit 1
fi

echo "==> Configuration"
print_config
echo "Stack name:            ${STACK_NAME}"
echo "Email sender:          ${EMAIL_SENDER}"
echo "Email recipients:      ${EMAIL_RECIPIENTS}"
echo "Detail-type allowlist: ${EMAIL_DETAIL_TYPES}"
echo "Force send:            ${FORCE_SEND}"
echo "Marker expiration:     ${MARKER_EXPIRATION_DAYS} days"
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
        "EmailSender=${EMAIL_SENDER}" \
        "EmailRecipients=${EMAIL_RECIPIENTS}" \
        "EmailDetailTypes=${EMAIL_DETAIL_TYPES}" \
        "ConsoleUrlTemplate=${CONSOLE_URL_TEMPLATE}" \
        "ForceSend=${FORCE_SEND}" \
        "MarkerExpirationDays=${MARKER_EXPIRATION_DAYS}"

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
try:
    with open(path) as f:
        state = json.load(f)
except FileNotFoundError:
    state = {}
state["emailNotifierStackName"] = stack_name
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
PY

echo
echo "Done. Verify SES is out of sandbox or all recipients are verified."
echo "Test with:"
echo "  aws ses send-email --from \"${EMAIL_SENDER}\" --to \"${EMAIL_RECIPIENTS%%,*}\" \\"
echo "    --subject 'SES verification test' --text 'Test from ${STACK_NAME}' --region ${REGION}"
