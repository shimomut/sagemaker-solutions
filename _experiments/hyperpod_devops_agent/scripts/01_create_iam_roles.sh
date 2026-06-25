#!/usr/bin/env bash
# Creates the two IAM roles required by AWS DevOps Agent:
#
#   1. <AGENT_SPACE_ROLE_NAME>  - assumed by aidevops.amazonaws.com to discover
#                                  and read AWS resources during investigations.
#                                  Managed policy: AIDevOpsAgentAccessPolicy.
#                                  Plus an inline policy allowing the
#                                  Resource Explorer service-linked role to be
#                                  created on first use.
#
#   2. <WEBAPP_ROLE_NAME>       - assumed by aidevops.amazonaws.com to back the
#                                  Operator web app (chat, investigations,
#                                  knowledge management).
#                                  Managed policy: AIDevOpsOperatorAppAccessPolicy.
#
# Both trust policies follow the pattern from the UG "AWS DevOps Agent CLI
# onboarding guide", scoping with aws:SourceAccount and aws:SourceArn so only
# this account's agentspace/* can assume them.
#
# Re-runnable: if a role already exists, the script attaches/updates policies
# without recreating it.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/config.sh"

echo "==> Configuration"
print_config
echo

agent_trust_policy() {
    cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": { "Service": "aidevops.amazonaws.com" },
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": { "aws:SourceAccount": "${ACCOUNT_ID}" },
                "ArnLike": { "aws:SourceArn": "arn:aws:aidevops:${REGION}:${ACCOUNT_ID}:agentspace/*" }
            }
        }
    ]
}
EOF
}

webapp_trust_policy() {
    cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": { "Service": "aidevops.amazonaws.com" },
            "Action": [ "sts:AssumeRole", "sts:TagSession" ],
            "Condition": {
                "StringEquals": { "aws:SourceAccount": "${ACCOUNT_ID}" },
                "ArnLike": { "aws:SourceArn": "arn:aws:aidevops:${REGION}:${ACCOUNT_ID}:agentspace/*" }
            }
        }
    ]
}
EOF
}

resource_explorer_inline_policy() {
    cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowCreateServiceLinkedRoles",
            "Effect": "Allow",
            "Action": [ "iam:CreateServiceLinkedRole" ],
            "Resource": [
                "arn:aws:iam::${ACCOUNT_ID}:role/aws-service-role/resource-explorer-2.amazonaws.com/AWSServiceRoleForResourceExplorer"
            ]
        }
    ]
}
EOF
}

ensure_role() {
    local role_name="$1"
    local trust_policy="$2"

    if aws iam get-role --role-name "${role_name}" >/dev/null 2>&1; then
        echo "    role ${role_name} already exists, refreshing trust policy"
        aws iam update-assume-role-policy \
            --role-name "${role_name}" \
            --policy-document "${trust_policy}"
    else
        echo "    creating role ${role_name}"
        aws iam create-role \
            --role-name "${role_name}" \
            --assume-role-policy-document "${trust_policy}" \
            --description "AWS DevOps Agent role (managed by hyperpod_devops_agent experiment)" \
            >/dev/null
    fi
}

echo "==> Step 1/2: ${AGENT_SPACE_ROLE_NAME}"
ensure_role "${AGENT_SPACE_ROLE_NAME}" "$(agent_trust_policy)"
aws iam attach-role-policy \
    --role-name "${AGENT_SPACE_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam put-role-policy \
    --role-name "${AGENT_SPACE_ROLE_NAME}" \
    --policy-name AllowCreateServiceLinkedRoles \
    --policy-document "$(resource_explorer_inline_policy)"
AGENT_SPACE_ROLE_ARN="$(aws iam get-role --role-name "${AGENT_SPACE_ROLE_NAME}" --query 'Role.Arn' --output text)"
echo "    ARN: ${AGENT_SPACE_ROLE_ARN}"

echo
echo "==> Step 2/2: ${WEBAPP_ROLE_NAME}"
ensure_role "${WEBAPP_ROLE_NAME}" "$(webapp_trust_policy)"
aws iam attach-role-policy \
    --role-name "${WEBAPP_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
WEBAPP_ROLE_ARN="$(aws iam get-role --role-name "${WEBAPP_ROLE_NAME}" --query 'Role.Arn' --output text)"
echo "    ARN: ${WEBAPP_ROLE_ARN}"

python3 - "${STATE_FILE}" "${AGENT_SPACE_ROLE_ARN}" "${WEBAPP_ROLE_ARN}" <<'PY'
import json, os, sys
path, agent_role_arn, webapp_role_arn = sys.argv[1:]
state = {}
if os.path.exists(path):
    with open(path) as f:
        state = json.load(f)
state["agentSpaceRoleArn"] = agent_role_arn
state["webappRoleArn"] = webapp_role_arn
with open(path, "w") as f:
    json.dump(state, f, indent=2, sort_keys=True)
print(f"    wrote {path}")
PY

echo
echo "Done. Both IAM roles are ready."
