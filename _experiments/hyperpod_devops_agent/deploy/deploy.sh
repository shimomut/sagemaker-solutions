#!/usr/bin/env bash
# One-command deploy of the unified HyperPod x DevOps Agent stack.
#
#   1. Resolve region + account.
#   2. Read params.json (flat key->value map; see params.example.json).
#   3. Auto-discover the underlying EKS cluster name from the HyperPod cluster
#      (empty for Slurm -> EKS access is skipped by the template).
#   4. Ensure the S3 assets bucket exists, then sync the skills into it and
#      capture the manifest + content-hash version.
#   5. Embed the Lambda sources into template.embedded.yaml.
#   6. aws cloudformation deploy with the assembled parameters.
#
# Env overrides: REGION, STACK_NAME, PARAMS_FILE, SKIP_SKILLS=yes.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${STACK_NAME:=hyperpod-devops-agent}"
: "${PARAMS_FILE:=${HERE}/params.json}"
: "${TEMPLATE_SRC:=${HERE}/template.yaml}"
: "${TEMPLATE_OUT:=${HERE}/template.embedded.yaml}"

if [[ ! -f "${PARAMS_FILE}" ]]; then
    echo "Error: ${PARAMS_FILE} not found. Copy deploy/params.example.json to deploy/params.json and edit it." >&2
    exit 1
fi

# Region: env override, else params.json, else AWS CLI default.
if [[ -z "${REGION:-}" ]]; then
    REGION="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('Region',''))" "${PARAMS_FILE}")"
fi
if [[ -z "${REGION}" ]]; then
    REGION="$(aws configure get region 2>/dev/null || echo "")"
fi
if [[ -z "${REGION}" ]]; then
    echo "Error: no region. Set REGION=..., add \"Region\" to params.json, or 'aws configure set region <region>'." >&2
    exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

# ------------------------------------------------------------ read params.json
# Emit "Key=Value" lines for every entry that is a real CloudFormation
# parameter (skip __-prefixed keys and the Region helper).
mapfile -t USER_PARAMS < <(python3 - "${PARAMS_FILE}" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
reserved = {"Region"}
for k, v in data.items():
    if k.startswith("__") or k in reserved:
        continue
    print(f"{k}={v}")
PY
)

HYPERPOD_CLUSTER_NAME="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('HyperPodClusterName',''))" "${PARAMS_FILE}")"
if [[ -z "${HYPERPOD_CLUSTER_NAME}" ]]; then
    echo "Error: HyperPodClusterName is required in ${PARAMS_FILE}." >&2
    exit 1
fi

echo "==> Configuration"
echo "    Region:           ${REGION}"
echo "    Account:          ${ACCOUNT_ID}"
echo "    HyperPod cluster: ${HYPERPOD_CLUSTER_NAME}"
echo "    Stack name:       ${STACK_NAME}"

# ------------------------------------------------- auto-discover EKS cluster name
EKS_ARN="$(aws sagemaker describe-cluster \
    --cluster-name "${HYPERPOD_CLUSTER_NAME}" \
    --region "${REGION}" \
    --query 'Orchestrator.Eks.ClusterArn' \
    --output text 2>/dev/null || echo "")"
if [[ -n "${EKS_ARN}" && "${EKS_ARN}" != "None" ]]; then
    EKS_CLUSTER_NAME="${EKS_ARN##*/}"
    echo "    EKS cluster:      ${EKS_CLUSTER_NAME} (auto-discovered)"
    # Pre-flight: EKS access entries need API/API_AND_CONFIG_MAP auth mode.
    AUTH_MODE="$(aws eks describe-cluster --name "${EKS_CLUSTER_NAME}" --region "${REGION}" \
        --query 'cluster.accessConfig.authenticationMode' --output text 2>/dev/null || echo "")"
    if [[ "${AUTH_MODE}" != "API" && "${AUTH_MODE}" != "API_AND_CONFIG_MAP" ]]; then
        echo "Error: EKS cluster '${EKS_CLUSTER_NAME}' has authenticationMode=${AUTH_MODE}." >&2
        echo "  DevOps Agent EKS access requires API or API_AND_CONFIG_MAP. Update with:" >&2
        echo "  aws eks update-cluster-config --name ${EKS_CLUSTER_NAME} --region ${REGION} \\" >&2
        echo "      --access-config authenticationMode=API_AND_CONFIG_MAP" >&2
        exit 1
    fi
else
    EKS_CLUSTER_NAME=""
    echo "    EKS cluster:      <none — Slurm or undiscovered; EKS access skipped>"
fi

# ------------------------------------------------------------------ sync skills
ASSETS_BUCKET=""
SKILLS_VERSION="none"
SKILLS_MANIFEST="[]"
if [[ "${SKIP_SKILLS:-no}" != "yes" ]]; then
    ASSETS_BUCKET="hyperpod-devops-agent-assets-${ACCOUNT_ID}-${REGION}"
    echo
    echo "==> Ensuring assets bucket s3://${ASSETS_BUCKET}"
    if ! aws s3api head-bucket --bucket "${ASSETS_BUCKET}" --region "${REGION}" 2>/dev/null; then
        if [[ "${REGION}" == "us-east-1" ]]; then
            aws s3api create-bucket --bucket "${ASSETS_BUCKET}" --region "${REGION}" >/dev/null
        else
            aws s3api create-bucket --bucket "${ASSETS_BUCKET}" --region "${REGION}" \
                --create-bucket-configuration "LocationConstraint=${REGION}" >/dev/null
        fi
        echo "    created bucket"
    else
        echo "    bucket already exists"
    fi

    echo
    echo "==> Syncing skills to S3"
    SYNC_JSON="$(python3 "${HERE}/build.py" sync-skills --bucket "${ASSETS_BUCKET}" --region "${REGION}")"
    SKILLS_VERSION="$(echo "${SYNC_JSON}" | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])")"
    SKILLS_MANIFEST="$(echo "${SYNC_JSON}" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['manifest']))")"
    echo "    skills version: ${SKILLS_VERSION}"
else
    echo
    echo "==> SKIP_SKILLS=yes — skill upload disabled for this deploy"
fi

# ------------------------------------------------------------------ embed + deploy
echo
echo "==> Embedding Lambda code into template"
python3 "${HERE}/build.py" embed --in "${TEMPLATE_SRC}" --out "${TEMPLATE_OUT}"

# Assemble parameter overrides: user params first, then the auto-derived ones
# (later values win in aws cloudformation deploy, so auto-derived override any
# stale user entries for these managed keys).
PARAMS=("${USER_PARAMS[@]}")
PARAMS+=("EksClusterName=${EKS_CLUSTER_NAME}")
PARAMS+=("AssetsBucket=${ASSETS_BUCKET}")
PARAMS+=("SkillsVersion=${SKILLS_VERSION}")
PARAMS+=("SkillsManifest=${SKILLS_MANIFEST}")

echo
echo "==> Deploying stack ${STACK_NAME}"
aws cloudformation deploy \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --template-file "${TEMPLATE_OUT}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "${PARAMS[@]}"

echo
echo "==> Stack outputs"
aws cloudformation describe-stacks \
    --region "${REGION}" \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

echo
echo "Done."
