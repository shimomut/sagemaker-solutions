#!/usr/bin/env bash
# Stores the DevOps Agent generic webhook URL + HMAC secret in Secrets Manager
# and records the resulting ARN in .state.json.
#
# Source of the credentials, in order:
#   1. WEBHOOK_URL + WEBHOOK_HMAC_SECRET env vars (explicit override).
#   2. webhookUrl + webhookSecret in .state.json (written by
#      02_create_agent_space.sh after register-service + associate-service).
#   3. Interactive prompt (last resort — e.g. webhook generated manually
#      in the console).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

: "${SECRET_NAME:=hyperpod-devops-agent/webhook}"

echo "==> Configuration"
print_config
echo "Secret name: ${SECRET_NAME}"
echo

# Fall back to state-file values written by 02_create_agent_space.sh.
if [[ -z "${WEBHOOK_URL:-}" || -z "${WEBHOOK_HMAC_SECRET:-}" ]]; then
    if [[ -f "${STATE_FILE}" ]]; then
        STATE_URL="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('webhookUrl',''))" "${STATE_FILE}" 2>/dev/null || echo "")"
        STATE_SECRET="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('webhookSecret',''))" "${STATE_FILE}" 2>/dev/null || echo "")"
        : "${WEBHOOK_URL:=${STATE_URL}}"
        : "${WEBHOOK_HMAC_SECRET:=${STATE_SECRET}}"
        if [[ -n "${WEBHOOK_URL}" && -n "${WEBHOOK_HMAC_SECRET}" ]]; then
            echo "    using webhook credentials from ${STATE_FILE}"
        fi
    fi
fi

if [[ -z "${WEBHOOK_URL:-}" ]]; then
    read -rp "Webhook URL: " WEBHOOK_URL
fi
if [[ -z "${WEBHOOK_HMAC_SECRET:-}" ]]; then
    read -rsp "Webhook HMAC secret: " WEBHOOK_HMAC_SECRET
    echo
fi

if [[ -z "${WEBHOOK_URL}" || -z "${WEBHOOK_HMAC_SECRET}" ]]; then
    echo "Error: both WEBHOOK_URL and WEBHOOK_HMAC_SECRET are required." >&2
    exit 1
fi

SECRET_VALUE="$(python3 -c 'import json,sys; print(json.dumps({"url": sys.argv[1], "secret": sys.argv[2]}))' "${WEBHOOK_URL}" "${WEBHOOK_HMAC_SECRET}")"

echo "==> Creating or updating Secrets Manager secret ${SECRET_NAME}"
if aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --region "${REGION}" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value \
        --region "${REGION}" \
        --secret-id "${SECRET_NAME}" \
        --secret-string "${SECRET_VALUE}" \
        >/dev/null
    echo "    updated existing secret"
else
    aws secretsmanager create-secret \
        --region "${REGION}" \
        --name "${SECRET_NAME}" \
        --description "AWS DevOps Agent generic webhook for HyperPod cluster events" \
        --secret-string "${SECRET_VALUE}" \
        >/dev/null
    echo "    created new secret"
fi

SECRET_ARN="$(aws secretsmanager describe-secret \
    --region "${REGION}" \
    --secret-id "${SECRET_NAME}" \
    --query ARN --output text)"

python3 - "${STATE_FILE}" "${SECRET_ARN}" "${SECRET_NAME}" <<'PY'
import json, os, sys
path, arn, name = sys.argv[1:]
state = {}
if os.path.exists(path):
    with open(path) as f:
        state = json.load(f)
state["webhookSecretName"] = name
state["webhookSecretArn"] = arn
# Now that the secret is stored in Secrets Manager, drop the plaintext copy
# from the local state file (the URL is fine to keep; the HMAC secret is not).
state.pop("webhookSecret", None)
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
print(f"    wrote {path}")
PY

echo
echo "Secret ARN: ${SECRET_ARN}"
