#!/usr/bin/env bash
# Creates the Agent Space, associates the primary AWS account, enables the
# Operator web app with IAM authentication, and provisions a generic-webhook
# event channel. Idempotent: if an Agent Space with the configured name
# already exists in this region, the script reuses it; if a webhook is
# already associated, it reuses that too.
#
# Persists agentSpaceId, eventChannelServiceId, eventChannelAssociationId,
# webhookUrl, and webhookSecret to .state.json.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make iam-roles' first." >&2
    exit 1
fi

AGENT_SPACE_ROLE_ARN="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['agentSpaceRoleArn'])" "${STATE_FILE}")"
WEBAPP_ROLE_ARN="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['webappRoleArn'])" "${STATE_FILE}")"

echo "==> Configuration"
print_config
echo "Agent Space role ARN: ${AGENT_SPACE_ROLE_ARN}"
echo "Webapp role ARN:      ${WEBAPP_ROLE_ARN}"
echo

echo "==> Step 1/4: Create or reuse Agent Space '${AGENT_SPACE_NAME}'"
EXISTING_ID="$(aws devops-agent list-agent-spaces \
    --region "${REGION}" \
    --query "agentSpaces[?name=='${AGENT_SPACE_NAME}'].agentSpaceId | [0]" \
    --output text 2>/dev/null || true)"

if [[ -n "${EXISTING_ID}" && "${EXISTING_ID}" != "None" ]]; then
    AGENT_SPACE_ID="${EXISTING_ID}"
    echo "    reusing existing Agent Space ${AGENT_SPACE_ID}"
else
    echo "    creating Agent Space"
    AGENT_SPACE_ID="$(aws devops-agent create-agent-space \
        --region "${REGION}" \
        --name "${AGENT_SPACE_NAME}" \
        --description "${AGENT_SPACE_DESCRIPTION}" \
        --query 'agentSpace.agentSpaceId' \
        --output text)"
    echo "    created ${AGENT_SPACE_ID}"
fi

echo
echo "==> Step 2/4: Associate primary AWS account ${ACCOUNT_ID} as 'monitor'"
ASSOCIATE_CONFIG=$(cat <<EOF
{
    "aws": {
        "assumableRoleArn": "${AGENT_SPACE_ROLE_ARN}",
        "accountId": "${ACCOUNT_ID}",
        "accountType": "monitor"
    }
}
EOF
)
aws devops-agent associate-service \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --service-id aws \
    --configuration "${ASSOCIATE_CONFIG}" \
    >/dev/null
echo "    associated"

echo
echo "==> Step 3/4: Enable Operator web app (IAM auth)"
aws devops-agent enable-operator-app \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --auth-flow iam \
    --operator-app-role-arn "${WEBAPP_ROLE_ARN}" \
    >/dev/null
echo "    operator app enabled"

echo
echo "==> Step 4/4: Provision generic-webhook event channel"
# Reuse an existing eventChannel association if one is already present.
ASSOC_JSON="$(aws devops-agent list-associations \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --query "associations[?serviceId!=null && configuration.eventChannel!=null] | [0]" \
    --output json 2>/dev/null)"

if [[ "${ASSOC_JSON}" != "null" && "${ASSOC_JSON}" != "" ]]; then
    ASSOC_ID="$(echo "${ASSOC_JSON}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('associationId',''))")"
    SVC_ID="$(echo "${ASSOC_JSON}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('serviceId',''))")"
    echo "    eventChannel already associated (associationId=${ASSOC_ID})"
    WEBHOOK_JSON="$(aws devops-agent list-webhooks \
        --region "${REGION}" \
        --agent-space-id "${AGENT_SPACE_ID}" \
        --association-id "${ASSOC_ID}" \
        --query 'webhooks[0]' \
        --output json 2>/dev/null)"
    WEBHOOK_URL="$(echo "${WEBHOOK_JSON}" | python3 -c "import json,sys; d=json.load(sys.stdin) or {}; print(d.get('webhookUrl',''))")"
    # list-webhooks does NOT return the HMAC secret (it's shown once on create).
    WEBHOOK_SECRET=""
    if [[ -z "${WEBHOOK_URL}" ]]; then
        echo "    WARNING: eventChannel association exists but no webhook found — likely manual cleanup needed"
    else
        echo "    reusing webhook URL ${WEBHOOK_URL}"
        echo "    (HMAC secret is not retrievable from list-webhooks — only available at create time)"
    fi
else
    echo "    registering eventChannel service"
    SVC_ID="$(aws devops-agent register-service \
        --region "${REGION}" \
        --service eventChannel \
        --service-details '{"eventChannel":{"type":"webhook"}}' \
        --query 'serviceId' \
        --output text)"
    echo "    serviceId: ${SVC_ID}"

    echo "    associating eventChannel to agent space"
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

python3 - "${STATE_FILE}" "${AGENT_SPACE_ID}" "${SVC_ID}" "${ASSOC_ID:-}" "${WEBHOOK_URL:-}" "${WEBHOOK_SECRET:-}" <<'PY'
import json, sys
path, agent_space_id, svc_id, assoc_id, webhook_url, webhook_secret = sys.argv[1:]
with open(path) as f:
    state = json.load(f)
state["agentSpaceId"] = agent_space_id
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
echo "Agent Space ID: ${AGENT_SPACE_ID}"
echo "Open the operator web app from the AWS DevOps Agent console:"
echo "  https://${REGION}.console.aws.amazon.com/aidevops/home?region=${REGION}#/agentspaces/${AGENT_SPACE_ID}"
