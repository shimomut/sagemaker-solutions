# HyperPod EKS with RIG - Existing VPC Setup

This solution demonstrates how to set up an existing VPC/Subnets for a HyperPod EKS cluster with RIG (Resilience Instance Groups), without internet access (no Internet Gateway or NAT Gateway).

## Architecture

- **VPC** with DNS support and DNS hostnames enabled
- **3 Private Subnets:**
  - 1x HyperPod nodes subnet (`/21` - 2046 usable IPs)
  - 2x EKS cluster subnets (`/28` - 14 usable IPs each, in separate AZs)
- **VPC Endpoints:**
  - S3 (Gateway type)
- **Optional Internet Access** (disabled by default):
  - 1x Public subnet with Internet Gateway
  - NAT Gateway for private subnet outbound traffic
  - When disabled, verifies RIG works in a fully private network

## Usage

### 1. Deploy the CloudFormation stack

```bash
aws cloudformation deploy \
    --template-file vpc.yaml \
    --stack-name hyperpod-eks-rig-vpc \
    --region <your-region> \
    --parameter-overrides \
        HyperPodSubnetAz=<az-id-for-hyperpod> \
        EksSubnet1Az=<az-id-for-eks-1> \
        EksSubnet2Az=<az-id-for-eks-2>
```

To enable internet access (creates public subnet, Internet Gateway, and NAT Gateway):

```bash
aws cloudformation deploy \
    --template-file vpc.yaml \
    --stack-name hyperpod-eks-rig-vpc \
    --region <your-region> \
    --parameter-overrides \
        HyperPodSubnetAz=<az-id-for-hyperpod> \
        EksSubnet1Az=<az-id-for-eks-1> \
        EksSubnet2Az=<az-id-for-eks-2> \
        EnableInternetAccess=true
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
