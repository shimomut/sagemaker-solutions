#!/usr/bin/env bash
# Deploy the IAM roles CloudFormation stack: AgentSpace role + Webapp role.
#
# Re-runnable: CloudFormation handles existing-resource updates idempotently.
#
# Outputs the two role ARNs into the local state file so later steps can
# reference them.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-iam-roles}"
TEMPLATE_FILE="${ROOT}/iam_roles/template.yaml"

echo "==> Configuration"
print_config
echo "Stack name: ${STACK_NAME}"
echo

echo "==> Deploying stack ${STACK_NAME}"
aws cloudformation deploy \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --template-file "${TEMPLATE_FILE}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        "AgentSpaceRoleName=${AGENT_SPACE_ROLE_NAME}" \
        "WebappRoleName=${WEBAPP_ROLE_NAME}"

echo
echo "==> Stack outputs"
aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

AGENT_SPACE_ROLE_ARN="$(aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='AgentSpaceRoleArn'].OutputValue | [0]" \
    --output text)"
WEBAPP_ROLE_ARN="$(aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='WebappRoleArn'].OutputValue | [0]" \
    --output text)"

python3 - "${STATE_FILE}" "${AGENT_SPACE_ROLE_ARN}" "${WEBAPP_ROLE_ARN}" "${STACK_NAME}" <<'PY'
import json, os, sys
path, agent_role_arn, webapp_role_arn, stack_name = sys.argv[1:]
state = {}
if os.path.exists(path):
    with open(path) as f:
        state = json.load(f)
state["agentSpaceRoleArn"] = agent_role_arn
state["webappRoleArn"] = webapp_role_arn
state["iamRolesStackName"] = stack_name
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
print(f"    wrote {path}")
PY

echo
echo "Done."
