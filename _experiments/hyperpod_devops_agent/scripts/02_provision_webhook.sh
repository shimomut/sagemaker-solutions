#!/usr/bin/env bash
# Provisions a generic-webhook event channel against the Agent Space (which
# is already created by 01_deploy_foundation.sh).
#
# CloudFormation today does NOT cover the eventChannel service: the allowed
# AWS::DevOpsAgent::Service ServiceType values exclude "eventChannel", and
# even AWS::DevOpsAgent::Association with EventChannel config doesn't expose
# the generated webhook URL/HMAC secret as a Fn::GetAtt attribute. So this
# step stays imperative: register-service + associate-service via the CLI,
# capture the credentials from the response (shown only once), and stash
# them into .state.json. The next step (04_create_webhook_secret.sh) copies
# them to Secrets Manager and strips the plaintext from disk.
#
# Idempotent: if an eventChannel association is already attached to the
# Agent Space, the script reuses it (but cannot recover the HMAC secret
# from list-webhooks).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make foundation' first." >&2
    exit 1
fi

AGENT_SPACE_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('agentSpaceId',''))" "${STATE_FILE}")"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    echo "Error: agentSpaceId missing from ${STATE_FILE}. Run 'make foundation' first." >&2
    exit 1
fi

echo "==> Configuration"
print_config
echo "Agent Space ID: ${AGENT_SPACE_ID}"
echo

# Reuse an existing eventChannel association if one is already present.
ASSOC_JSON="$(aws devops-agent list-associations \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --query "associations[?configuration.eventChannel!=null] | [0]" \
    --output json 2>/dev/null)"

if [[ "${ASSOC_JSON}" != "null" && "${ASSOC_JSON}" != "" ]]; then
    ASSOC_ID="$(echo "${ASSOC_JSON}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('associationId',''))")"
    SVC_ID="$(echo "${ASSOC_JSON}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('serviceId',''))")"
    echo "==> Existing eventChannel association detected (associationId=${ASSOC_ID})"
    WEBHOOK_JSON="$(aws devops-agent list-webhooks \
        --region "${REGION}" \
        --agent-space-id "${AGENT_SPACE_ID}" \
        --association-id "${ASSOC_ID}" \
        --query 'webhooks[0]' \
        --output json 2>/dev/null)"
    WEBHOOK_URL="$(echo "${WEBHOOK_JSON}" | python3 -c "import json,sys; d=json.load(sys.stdin) or {}; print(d.get('webhookUrl',''))")"
    # list-webhooks does NOT return the HMAC secret (only available at create time).
    WEBHOOK_SECRET=""
    if [[ -z "${WEBHOOK_URL}" ]]; then
        echo "    WARNING: association exists but no webhook found — manual cleanup likely needed"
    else
        echo "    reusing webhook URL ${WEBHOOK_URL}"
        echo "    (HMAC secret is not retrievable — only returned at create time)"
    fi
else
    echo "==> Registering eventChannel service"
    SVC_ID="$(aws devops-agent register-service \
        --region "${REGION}" \
        --service eventChannel \
        --service-details '{"eventChannel":{"type":"webhook"}}' \
        --query 'serviceId' \
        --output text)"
    echo "    serviceId: ${SVC_ID}"

    echo
    echo "==> Associating eventChannel to Agent Space"
    ASSOC_RESPONSE="$(aws devops-agent associate-service \
        --region "${REGION}" \
        --agent-space-id "${AGENT_SPACE_ID}" \
        --service-id "${SVC_ID}" \
        --configuration '{"eventChannel": {}}' \
        --output json)"
    ASSOC_ID="$(echo "${ASSOC_RESPONSE}" | python3 -c "import json,sys; print(json.load(sys.stdin)['association']['associationId'])")"
    WEBHOOK_URL="$(echo "${ASSOC_RESPONSE}" | python3 -c "import json,sys; print(json.load(sys.stdin)['webhook']['webhookUrl'])")"
    WEBHOOK_SECRET="$(echo "${ASSOC_RESPONSE}" | python3 -c "import json,sys; print(json.load(sys.stdin)['webhook']['webhookSecret'])")"
    echo "    associationId: ${ASSOC_ID}"
    echo "    webhookUrl:    ${WEBHOOK_URL}"
fi

python3 - "${STATE_FILE}" "${SVC_ID}" "${ASSOC_ID:-}" "${WEBHOOK_URL:-}" "${WEBHOOK_SECRET:-}" <<'PY'
import json, sys
path, svc_id, assoc_id, webhook_url, webhook_secret = sys.argv[1:]
with open(path) as f:
    state = json.load(f)
if svc_id:
    state["eventChannelServiceId"] = svc_id
if assoc_id:
    state["eventChannelAssociationId"] = assoc_id
if webhook_url:
    state["webhookUrl"] = webhook_url
if webhook_secret:
    state["webhookSecret"] = webhook_secret
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
print(f"    wrote {path}")
PY

echo
echo "Done. Run 'make webhook-secret' to copy credentials into Secrets Manager."
