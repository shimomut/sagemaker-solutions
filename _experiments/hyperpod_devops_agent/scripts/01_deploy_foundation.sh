#!/usr/bin/env bash
# Deploy the foundation CloudFormation stack: IAM roles + AgentSpace +
# AWS monitor association. Uses native AWS::DevOpsAgent::AgentSpace and
# AWS::DevOpsAgent::Association resources.
#
# Re-runnable: CloudFormation handles existing-resource updates idempotently.
#
# Outputs role ARNs and Agent Space ID into the local state file so later
# steps (EKS access entry, webhook bridge, skill upload) can reference them.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${STACK_NAME:=hyperpod-devops-agent-foundation}"
TEMPLATE_FILE="${ROOT}/foundation/template.yaml"

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
        "WebappRoleName=${WEBAPP_ROLE_NAME}" \
        "AgentSpaceName=${AGENT_SPACE_NAME}" \
        "AgentSpaceDescription=${AGENT_SPACE_DESCRIPTION}"

echo
echo "==> Stack outputs"
aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

get_output() {
    aws cloudformation describe-stacks \
        --region "${REGION}" \
        --stack-name "${STACK_NAME}" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" \
        --output text
}

AGENT_SPACE_ROLE_ARN="$(get_output AgentSpaceRoleArn)"
WEBAPP_ROLE_ARN="$(get_output WebappRoleArn)"
AGENT_SPACE_ID="$(get_output AgentSpaceId)"
AWS_ASSOCIATION_ID="$(get_output AwsAssociationId)"

python3 - "${STATE_FILE}" "${AGENT_SPACE_ROLE_ARN}" "${WEBAPP_ROLE_ARN}" "${AGENT_SPACE_ID}" "${AWS_ASSOCIATION_ID}" "${STACK_NAME}" <<'PY'
import json, os, sys
path, agent_role_arn, webapp_role_arn, agent_space_id, aws_assoc_id, stack_name = sys.argv[1:]
state = {}
if os.path.exists(path):
    with open(path) as f:
        state = json.load(f)
state["agentSpaceRoleArn"] = agent_role_arn
state["webappRoleArn"] = webapp_role_arn
state["agentSpaceId"] = agent_space_id
state["awsAssociationId"] = aws_assoc_id
state["foundationStackName"] = stack_name
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
print(f"    wrote {path}")
PY

echo
echo "Agent Space console:"
echo "  https://${REGION}.console.aws.amazon.com/aidevops/home?region=${REGION}#/agentspaces/${AGENT_SPACE_ID}"
echo
echo "Done."
