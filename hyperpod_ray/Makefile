SHELL := /bin/bash

# ===== Configuration =====

AWS_REGION ?= us-west-2

# Existing HyperPod EKS cluster to install Ray on.
EKS_CLUSTER_NAME ?=

STACK_NAME ?= hyperpod-ray
TEMPLATE ?= cfn/kuberay-operator.yaml

# Prefix for the resource names the stack creates. Must match the template's
# ResourceNamePrefix parameter, which is what the log group name is built from.
RESOURCE_PREFIX ?= hyperpod-ray

KUBERAY_VERSION ?= 1.7.0
KUBERAY_NAMESPACE ?= kuberay-operator
KUBERAY_RELEASE ?= kuberay-operator

# Only needed when the EKS cluster API endpoint is private.
INSTALLER_SUBNET_IDS ?=
INSTALLER_SECURITY_GROUP_IDS ?=

# Example RayCluster.
RAY_NAMESPACE ?= default
RAY_CLUSTER_NAME ?= ray-example
EXAMPLE_MANIFEST ?= examples/ray-cluster.yaml

# Documentation extraction. Shares the repository-level virtual environment.
VENV ?= ../.venv
PYTHON ?= $(VENV)/bin/python3
SOURCE_PDF ?= docs/sagemaker-dg.pdf
DOC_FIRST_PAGE ?= 2784
DOC_LAST_PAGE ?= 2849
DOC_MARKDOWN ?= docs/ray-on-hyperpod.md

AWS := aws --region $(AWS_REGION)

define require_cluster
	@if [ -z "$(EKS_CLUSTER_NAME)" ]; then \
		echo "EKS_CLUSTER_NAME is required, e.g. make $@ EKS_CLUSTER_NAME=my-cluster"; \
		exit 1; \
	fi
endef

.PHONY: help
help:
	@echo "Ray on HyperPod - CloudFormation setup"
	@echo ""
	@echo "Stack:"
	@echo "  make validate                          Validate the CloudFormation template"
	@echo "  make deploy EKS_CLUSTER_NAME=<name>    Create or update the stack"
	@echo "  make status                            Show stack status"
	@echo "  make outputs                           Show stack outputs"
	@echo "  make events                            Show recent stack events"
	@echo "  make logs                              Tail the installer function logs"
	@echo "  make delete                            Delete the stack (uninstalls KubeRay)"
	@echo ""
	@echo "Verify:"
	@echo "  make kubeconfig EKS_CLUSTER_NAME=<name>  Point kubectl at the cluster"
	@echo "  make operator-status                     Show the KubeRay operator pod"
	@echo "  make crds                                List the Ray custom resource definitions"
	@echo ""
	@echo "Example RayCluster:"
	@echo "  make deploy-example                    Apply $(EXAMPLE_MANIFEST)"
	@echo "  make list-clusters                     List RayClusters"
	@echo "  make describe-example                  Describe the example RayCluster"
	@echo "  make dashboard                         Port-forward the Ray Dashboard to :8265"
	@echo "  make delete-example                    Delete the example RayCluster"
	@echo ""
	@echo "Docs:"
	@echo "  make venv                              Install the extraction dependencies into $(VENV)"
	@echo "  make extract-docs                      Regenerate $(DOC_MARKDOWN) from the PDF"

# ===== CloudFormation stack =====

.PHONY: validate
validate:
	$(AWS) cloudformation validate-template \
		--template-body file://$(TEMPLATE) \
		--query 'Description' --output text

.PHONY: deploy
deploy:
	$(require_cluster)
	@overrides=( \
		EKSClusterName=$(EKS_CLUSTER_NAME) \
		ResourceNamePrefix=$(RESOURCE_PREFIX) \
		KubeRayVersion=$(KUBERAY_VERSION) \
		KubeRayNamespace=$(KUBERAY_NAMESPACE) \
		KubeRayReleaseName=$(KUBERAY_RELEASE) \
	); \
	if [ -n "$(INSTALLER_SUBNET_IDS)" ]; then \
		overrides+=( \
			InstallerSubnetIds=$(INSTALLER_SUBNET_IDS) \
			InstallerSecurityGroupIds=$(INSTALLER_SECURITY_GROUP_IDS) \
		); \
	fi; \
	set -x; \
	$(AWS) cloudformation deploy \
		--template-file $(TEMPLATE) \
		--stack-name $(STACK_NAME) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides "$${overrides[@]}"
	@$(MAKE) --no-print-directory outputs

.PHONY: status
status:
	$(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query 'Stacks[0].[StackStatus,StackStatusReason]' --output table

.PHONY: outputs
outputs:
	$(AWS) cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query 'Stacks[0].Outputs' --output table

.PHONY: events
events:
	$(AWS) cloudformation describe-stack-events \
		--stack-name $(STACK_NAME) \
		--query 'reverse(StackEvents[:25].[Timestamp,ResourceStatus,LogicalResourceId,ResourceStatusReason])' \
		--output table

.PHONY: logs
logs:
	$(AWS) logs tail /aws/lambda/$(RESOURCE_PREFIX)-kuberay-installer --follow

.PHONY: delete
delete:
	@echo "This uninstalls the KubeRay operator from the cluster."
	@echo "Delete your Ray resources first, or their deletions will never complete."
	@read -p "Delete stack $(STACK_NAME) in $(AWS_REGION)? [y/N] " reply; \
		[[ $$reply == [yY] ]] || exit 1
	$(AWS) cloudformation delete-stack --stack-name $(STACK_NAME)
	$(AWS) cloudformation wait stack-delete-complete --stack-name $(STACK_NAME)

# ===== Verification =====

.PHONY: kubeconfig
kubeconfig:
	$(require_cluster)
	$(AWS) eks update-kubeconfig --name $(EKS_CLUSTER_NAME)

.PHONY: operator-status
operator-status:
	kubectl get pods -n $(KUBERAY_NAMESPACE) -l app.kubernetes.io/name=kuberay-operator

.PHONY: crds
crds:
	kubectl get crds | grep ray.io

# ===== Example RayCluster =====

.PHONY: deploy-example
deploy-example:
	kubectl apply -f $(EXAMPLE_MANIFEST) -n $(RAY_NAMESPACE)

.PHONY: list-clusters
list-clusters:
	kubectl get rayclusters -n $(RAY_NAMESPACE)

.PHONY: describe-example
describe-example:
	kubectl describe raycluster $(RAY_CLUSTER_NAME) -n $(RAY_NAMESPACE)

.PHONY: dashboard
dashboard:
	@echo "Ray Dashboard: http://localhost:8265"
	kubectl port-forward -n $(RAY_NAMESPACE) service/$(RAY_CLUSTER_NAME)-head-svc 8265:8265

.PHONY: delete-example
delete-example:
	kubectl delete -f $(EXAMPLE_MANIFEST) -n $(RAY_NAMESPACE)

# ===== Documentation extraction =====

# The virtual environment is shared with the rest of the repository, so this
# installs into it rather than owning it. pip is a no-op once satisfied, so
# there is no stamp file to go stale.
.PHONY: venv
venv:
	@if [ ! -x $(PYTHON) ]; then python3 -m venv $(VENV); fi
	@$(VENV)/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

.PHONY: extract-docs
extract-docs: venv
	@if [ ! -f $(SOURCE_PDF) ]; then \
		echo "$(SOURCE_PDF) not found. Download the SageMaker AI Developer Guide PDF into docs/."; \
		exit 1; \
	fi
	$(PYTHON) scripts/extract_pdf_docs.py \
		--pdf $(SOURCE_PDF) \
		--first-page $(DOC_FIRST_PAGE) \
		--last-page $(DOC_LAST_PAGE) \
		--output $(DOC_MARKDOWN)
