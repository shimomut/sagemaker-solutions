#!/usr/bin/env bash
#
# Install the Mountpoint for Amazon S3 CSI driver on a HyperPod EKS cluster.
#
# This follows the official guide:
#   https://awslabs.github.io/ai-on-sagemaker-hyperpod/docs/eks-orchestration/getting-started/Set%20up%20an%20Amazon%20S3%20mountpoint
#
# Steps:
#   1. Associate an IAM OIDC provider with the cluster
#   2. Create an IAM policy granting access to the S3 bucket
#   3. Create an IAM role (role-only) bound to the s3-csi-driver-sa service account
#   4. Install the aws-mountpoint-s3-csi-driver EKS add-on
#
# All steps are idempotent and safe to re-run.
#
# Required environment variables:
#   EKS_CLUSTER_NAME, AWS_REGION, S3_BUCKET_NAME
# Optional:
#   S3_CSI_ROLE_NAME   (default: SM_HP_S3_CSI_ROLE)
#   S3_POLICY_NAME     (default: S3MountpointAccessPolicy)
#   READ_ONLY          (default: false; "true" omits write/delete permissions)

set -euo pipefail

: "${EKS_CLUSTER_NAME:?EKS_CLUSTER_NAME must be set}"
: "${AWS_REGION:?AWS_REGION must be set}"
: "${S3_BUCKET_NAME:?S3_BUCKET_NAME must be set}"
S3_CSI_ROLE_NAME="${S3_CSI_ROLE_NAME:-SM_HP_S3_CSI_ROLE}"
S3_POLICY_NAME="${S3_POLICY_NAME:-S3MountpointAccessPolicy}"
READ_ONLY="${READ_ONLY:-false}"

echo "==> Cluster:  ${EKS_CLUSTER_NAME} (${AWS_REGION})"
echo "==> Bucket:   ${S3_BUCKET_NAME}"
echo "==> Role:     ${S3_CSI_ROLE_NAME}"
echo "==> Policy:   ${S3_POLICY_NAME}"
echo "==> ReadOnly: ${READ_ONLY}"
echo

# --- Step 1: IAM OIDC provider -------------------------------------------------
echo "==> [1/4] Associating IAM OIDC provider (idempotent)..."
eksctl utils associate-iam-oidc-provider \
  --cluster "${EKS_CLUSTER_NAME}" \
  --region "${AWS_REGION}" \
  --approve

# --- Step 2: IAM policy --------------------------------------------------------
echo "==> [2/4] Ensuring IAM policy ${S3_POLICY_NAME} exists..."

if [[ "${READ_ONLY}" == "true" ]]; then
  OBJECT_ACTIONS='"s3:GetObject"'
else
  OBJECT_ACTIONS='"s3:GetObject",
                "s3:PutObject",
                "s3:AbortMultipartUpload",
                "s3:DeleteObject"'
fi

POLICY_DOC="$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MountpointFullBucketAccess",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${S3_BUCKET_NAME}"]
    },
    {
      "Sid": "MountpointObjectAccess",
      "Effect": "Allow",
      "Action": [
                ${OBJECT_ACTIONS}
      ],
      "Resource": ["arn:aws:s3:::${S3_BUCKET_NAME}/*"]
    }
  ]
}
EOF
)"

POLICY_ARN="$(aws iam list-policies \
  --query "Policies[?PolicyName=='${S3_POLICY_NAME}'].Arn" \
  --output text)"

if [[ -z "${POLICY_ARN}" || "${POLICY_ARN}" == "None" ]]; then
  POLICY_ARN="$(aws iam create-policy \
    --policy-name "${S3_POLICY_NAME}" \
    --policy-document "${POLICY_DOC}" \
    --query 'Policy.Arn' --output text)"
  echo "    Created policy: ${POLICY_ARN}"
else
  echo "    Policy already exists: ${POLICY_ARN}"
  echo "    (Not modifying an existing policy. Delete it first if the bucket changed.)"
fi

# --- Step 3: IAM role (role-only) ---------------------------------------------
echo "==> [3/4] Ensuring IAM role ${S3_CSI_ROLE_NAME} exists..."
if aws iam get-role --role-name "${S3_CSI_ROLE_NAME}" >/dev/null 2>&1; then
  echo "    Role already exists: ${S3_CSI_ROLE_NAME}"
else
  eksctl create iamserviceaccount \
    --name s3-csi-driver-sa \
    --namespace kube-system \
    --cluster "${EKS_CLUSTER_NAME}" \
    --attach-policy-arn "${POLICY_ARN}" \
    --approve \
    --role-name "${S3_CSI_ROLE_NAME}" \
    --region "${AWS_REGION}" \
    --role-only
  echo "    Created role: ${S3_CSI_ROLE_NAME}"
fi

ROLE_ARN="$(aws iam get-role --role-name "${S3_CSI_ROLE_NAME}" \
  --query 'Role.Arn' --output text)"

# --- Step 4: Install the CSI driver add-on ------------------------------------
echo "==> [4/4] Installing aws-mountpoint-s3-csi-driver add-on..."
eksctl create addon \
  --name aws-mountpoint-s3-csi-driver \
  --cluster "${EKS_CLUSTER_NAME}" \
  --region "${AWS_REGION}" \
  --service-account-role-arn "${ROLE_ARN}" \
  --force

echo
echo "==> Done. Verify with:"
echo "      kubectl get pods -n kube-system -l app=s3-csi-node"
echo "      kubectl get csidrivers | grep s3"
