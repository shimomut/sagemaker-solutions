# HyperPod EKS with RIG - Existing VPC Setup

This solution demonstrates how to set up an existing VPC/Subnets for a HyperPod EKS cluster with RIG (Resilience Instance Groups), without internet access (no Internet Gateway or NAT Gateway).

## Architecture

- **VPC** with DNS support and DNS hostnames enabled
- **3 Subnets:**
  - 1x HyperPod nodes subnet (`/21` - 2046 usable IPs)
  - 2x EKS cluster subnets (`/28` - 14 usable IPs each, in separate AZs)
- **VPC Endpoints** (to allow AWS service access without internet):
  - S3 (Gateway type)
  - Lambda (Interface type)
  - SQS (Interface type)
  - APS Workspaces (Interface type)
  - Grafana Workspace (Interface type)
- **No Internet Gateway or NAT Gateway** - verifying RIG works in a fully private network

## Usage

### 1. Deploy the CloudFormation stack

```bash
aws cloudformation deploy \
    --template-file vpc.yaml \
    --stack-name hyperpod-eks-rig-vpc \
    --region <your-region> \
    --parameter-overrides \
        HyperPodSubnetAz=<az-for-hyperpod> \
        EksSubnet1Az=<az-for-eks-1> \
        EksSubnet2Az=<az-for-eks-2>
```

### 2. Get the outputs

```bash
aws cloudformation describe-stacks \
    --stack-name hyperpod-eks-rig-vpc \
    --query 'Stacks[0].Outputs' \
    --output table
```

Note the VPC ID and Subnet IDs from the outputs.

### 3. Create HyperPod EKS cluster

1. Open the SageMaker HyperPod management console
2. Choose **Create cluster** with the **Custom setup** option
3. Select the VPC and subnets created by this stack:
   - For EKS cluster subnets: use `EksSubnet1Id` and `EksSubnet2Id`
   - For HyperPod node group subnet: use `HyperPodSubnetId`
4. Complete the remaining cluster configuration as needed

## Cleanup

```bash
aws cloudformation delete-stack --stack-name hyperpod-eks-rig-vpc
```

Note: Delete the HyperPod cluster before deleting the VPC stack.
