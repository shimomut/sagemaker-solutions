#!/usr/bin/env bash
#
# Uninstall the Mountpoint for Amazon S3 CSI driver add-on and (optionally) the
# IAM role and policy created by install_s3_csi_driver.sh.
#
# By default this only removes the add-on. Set DELETE_IAM=true to also delete the
# IAM role and policy.
#
# Required environment variables:
#   EKS_CLUSTER_NAME, AWS_REGION
# Optional:
#   S3_CSI_ROLE_NAME  (default: SM_HP_S3_CSI_ROLE)
#   S3_POLICY_NAME    (default: S3MountpointAccessPolicy)
#   DELETE_IAM        (default: false)

set -euo pipefail

: "${EKS_CLUSTER_NAME:?EKS_CLUSTER_NAME must be set}"
: "${AWS_REGION:?AWS_REGION must be set}"
S3_CSI_ROLE_NAME="${S3_CSI_ROLE_NAME:-SM_HP_S3_CSI_ROLE}"
S3_POLICY_NAME="${S3_POLICY_NAME:-S3MountpointAccessPolicy}"
DELETE_IAM="${DELETE_IAM:-false}"

echo "==> Deleting aws-mountpoint-s3-csi-driver add-on from ${EKS_CLUSTER_NAME}..."
eksctl delete addon \
  --name aws-mountpoint-s3-csi-driver \
  --cluster "${EKS_CLUSTER_NAME}" \
  --region "${AWS_REGION}" || true

if [[ "${DELETE_IAM}" != "true" ]]; then
  echo "==> Leaving IAM role/policy in place (set DELETE_IAM=true to remove them)."
  exit 0
fi

echo "==> Deleting IAM role ${S3_CSI_ROLE_NAME}..."
if aws iam get-role --role-name "${S3_CSI_ROLE_NAME}" >/dev/null 2>&1; then
  # Detach managed policies before deleting the role.
  for arn in $(aws iam list-attached-role-policies --role-name "${S3_CSI_ROLE_NAME}" \
      --query 'AttachedPolicies[].PolicyArn' --output text); do
    aws iam detach-role-policy --role-name "${S3_CSI_ROLE_NAME}" --policy-arn "${arn}" || true
  done
  aws iam delete-role --role-name "${S3_CSI_ROLE_NAME}" || true
fi

echo "==> Deleting IAM policy ${S3_POLICY_NAME}..."
POLICY_ARN="$(aws iam list-policies \
  --query "Policies[?PolicyName=='${S3_POLICY_NAME}'].Arn" --output text)"
if [[ -n "${POLICY_ARN}" && "${POLICY_ARN}" != "None" ]]; then
  aws iam delete-policy --policy-arn "${POLICY_ARN}" || true
fi

echo "==> Done."
