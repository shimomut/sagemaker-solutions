STACK_NAME ?= hyperpod-eks-rig-vpc
REGION ?= us-west-2
ENABLE_INTERNET_ACCESS ?= false

deploy:
	@if [ -z "$(HYPERPOD_SUBNET_AZ)" ] || [ -z "$(EKS_SUBNET1_AZ)" ] || [ -z "$(EKS_SUBNET2_AZ)" ]; then \
		echo "Error: HYPERPOD_SUBNET_AZ, EKS_SUBNET1_AZ, and EKS_SUBNET2_AZ are required"; \
		echo "Usage: make deploy HYPERPOD_SUBNET_AZ=usw2-az3 EKS_SUBNET1_AZ=usw2-az3 EKS_SUBNET2_AZ=usw2-az1 [REGION=us-west-2] [STACK_NAME=hyperpod-eks-rig-vpc] [ENABLE_INTERNET_ACCESS=false]"; \
		exit 1; \
	fi
	aws cloudformation deploy \
		--template-file vpc.yaml \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--capabilities CAPABILITY_NAMED_IAM \
		--parameter-overrides \
			HyperPodSubnetAz=$(HYPERPOD_SUBNET_AZ) \
			EksSubnet1Az=$(EKS_SUBNET1_AZ) \
			EksSubnet2Az=$(EKS_SUBNET2_AZ) \
			EnableInternetAccess=$(ENABLE_INTERNET_ACCESS)

outputs:
	aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--query 'Stacks[0].Outputs' \
		--output table

delete:
	aws cloudformation delete-stack \
		--stack-name $(STACK_NAME) \
		--region $(REGION)
	aws cloudformation wait stack-delete-complete \
		--stack-name $(STACK_NAME) \
		--region $(REGION)
