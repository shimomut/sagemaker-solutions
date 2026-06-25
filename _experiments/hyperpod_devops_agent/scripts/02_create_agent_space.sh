#!/usr/bin/env bash
# Creates the Agent Space, associates the primary AWS account, and enables the
# Operator web app with IAM authentication. Idempotent: if an Agent Space with
# the configured name already exists in this region, the script reuses it.
#
# Persists agentSpaceId to .state.json so the EKS access entry step can find it.

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

echo "==> Step 1/3: Create or reuse Agent Space '${AGENT_SPACE_NAME}'"
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
echo "==> Step 2/3: Associate primary AWS account ${ACCOUNT_ID} as 'monitor'"
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
echo "==> Step 3/3: Enable Operator web app (IAM auth)"
aws devops-agent enable-operator-app \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --auth-flow iam \
    --operator-app-role-arn "${WEBAPP_ROLE_ARN}" \
    >/dev/null
echo "    operator app enabled"

python3 - "${STATE_FILE}" "${AGENT_SPACE_ID}" <<'PY'
import json, sys
path, agent_space_id = sys.argv[1:]
with open(path) as f:
    state = json.load(f)
state["agentSpaceId"] = agent_space_id
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
print(f"    wrote {path}")
PY

echo
echo "Agent Space ID: ${AGENT_SPACE_ID}"
echo "Open the operator web app from the AWS DevOps Agent console:"
echo "  https://${REGION}.console.aws.amazon.com/aidevops/home?region=${REGION}#/agentspaces/${AGENT_SPACE_ID}"
