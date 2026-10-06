SHELL := /bin/bash

# ===== Configuration =====

AWS_REGION ?= us-west-2

# Existing HyperPod EKS cluster to install Ray on.
EKS_CLUSTER_NAME ?=

# SageMaker AI domain for Studio access to the cluster.
DOMAIN_STACK_NAME ?= hyperpod-ray-domain
DOMAIN_TEMPLATE ?= cfn/sagemaker-domain.yaml
DOMAIN_NAME ?= hyperpod-ray
USER_PROFILE_NAME ?= ray-user
# The HyperPod cluster, not the EKS cluster. Two different ARNs: the execution
# role's sagemaker:DescribeCluster is scoped to this one.
HYPERPOD_CLUSTER_NAME ?=
# Required by make deploy-domain. Look them up with:
#   aws eks describe-cluster --name $(EKS_CLUSTER_NAME) \
#     --query 'cluster.resourcesVpcConfig.{Vpc:vpcId,Subnets:subnetIds}'
DOMAIN_VPC_ID ?=
DOMAIN_SUBNET_IDS ?=
# Empty means whole-cluster access scope. Set to a comma-separated list to scope
# the HyperPod policies to namespaces instead. Always passed to the stack, even
# when empty: `cloudformation deploy` keeps the previous value for any parameter
# it is not given, so a conditional override could be set but never cleared.
ACCESS_SCOPE_NAMESPACES ?=
# The cluster-access policy checkboxes. Every parameter the stack has is passed on
# every deploy, because `cloudformation deploy` keeps the previous value for any it
# is not given - so a changed template default does nothing to an existing stack,
# and a variable you can set is one you can never clear.
ATTACH_TRAINING_POLICY ?= true
ATTACH_INFERENCE_POLICY ?= true
ATTACH_SPACE_POLICY ?= true
ATTACH_SPACE_TEMPLATE_POLICY ?= true
ATTACH_USER_CLUSTER_POLICY ?= true
SPACE_TEMPLATE_NAMESPACES ?= jupyter-k8s-system,jupyter-k8s-shared

# Only for the documented "custom Kubernetes RBAC role" route, where you bind your
# own ClusterRole to a group instead of using the HyperPod cluster-access policies.
# Leave empty to use the policies, which is what the defaults do.
KUBERNETES_GROUPS ?=

# KubeRay chart. Pin it: the developer guide's install command has no --version,
# so it tracks latest, and HyperPod needs >= 1.6.0 for RayCronJob and Ray's
# Kubernetes RBAC auth mode. 1.7.1 is the version this repo has verified.
KUBERAY_VERSION ?= 1.7.1
KUBERAY_NAMESPACE ?= kuberay-operator
KUBERAY_RELEASE ?= kuberay-operator

# Example RayCluster. EXAMPLE_FLAVOR picks the manifest and the cluster name
# together, so `make deploy-example EXAMPLE_FLAVOR=gpu` needs nothing else.
# Use the `space` flavour when a SageMaker Studio space will attach: it runs the
# same SageMaker Distribution image the space does, which is the only way the
# Python versions match and ray.init() connects.
EXAMPLE_FLAVOR ?= cpu
RAY_NAMESPACE ?= default
RAY_CLUSTER_NAME ?= ray-example-$(EXAMPLE_FLAVOR)
EXAMPLE_MANIFEST ?= examples/ray-cluster-$(EXAMPLE_FLAVOR).yaml

# The example workload scripts, delivered to the pods as a ConfigMap so the
# manifests stay self-contained (no image build, no S3, no working_dir upload).
EXAMPLES_CONFIGMAP ?= ray-examples
JOB ?= ray-data-job
SERVICE_NAME ?= ray-serve-example

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
	@echo "Ray on HyperPod - setup"
	@echo ""
	@echo "KubeRay operator (Helm, version $(KUBERAY_VERSION) in namespace $(KUBERAY_NAMESPACE)):"
	@echo "  make install-kuberay                     Install or upgrade the operator"
	@echo "  make kuberay-version                     Show the installed chart and image"
	@echo "  make uninstall-kuberay                   Uninstall the operator"
	@echo ""
	@echo "SageMaker AI domain (Studio access to the cluster):"
	@echo "  make deploy-domain EKS_CLUSTER_NAME=<name> DOMAIN_VPC_ID=<vpc> DOMAIN_SUBNET_IDS=<ids>"
	@echo "  make domain-outputs                      Show the domain ID, URL, and role"
	@echo "  make domain-access                       Show the EKS access policies granted"
	@echo "  make domain-events                       Show recent stack events"
	@echo "  make delete-domain                       Delete the domain stack"
	@echo ""
	@echo "Verify:"
	@echo "  make kubeconfig EKS_CLUSTER_NAME=<name>  Point kubectl at the cluster"
	@echo "  make operator-status                     Show the KubeRay operator pod"
	@echo "  make crds                                List the Ray custom resource definitions"
	@echo ""
	@echo "Example RayCluster (EXAMPLE_FLAVOR=cpu|gpu|space, currently $(EXAMPLE_FLAVOR)):"
	@echo "  make deploy-example                    Apply $(EXAMPLE_MANIFEST)"
	@echo "  make list-clusters                     List RayClusters"
	@echo "  make describe-example                  Describe the example RayCluster"
	@echo "  make dashboard                         Port-forward the Ray Dashboard to :8265"
	@echo "  make delete-example                    Delete the example RayCluster"
	@echo ""
	@echo "Example workloads (Ray Data, Ray Train, Ray Serve):"
	@echo "  make examples-configmap                Publish examples/scripts as a ConfigMap"
	@echo "  make run-job                           RayJob with its own cluster (Ray Data)"
	@echo "  make run-job-existing                  RayJob on the standing cluster (Ray Train)"
	@echo "  make list-jobs                         List RayJobs"
	@echo "  make job-logs JOB=<rayjob>             Follow a RayJob's driver output"
	@echo "  make delete-jobs                       Delete both RayJobs"
	@echo "  make deploy-service                    RayService for the Ray Serve app"
	@echo "  make service-status                    Show RayService readiness"
	@echo "  make service-request                   Port-forward and POST a test request"
	@echo "  make delete-service                    Delete the RayService"
	@echo ""
	@echo "Docs:"
	@echo "  make venv                              Install the extraction dependencies into $(VENV)"
	@echo "  make extract-docs                      Regenerate $(DOC_MARKDOWN) from the PDF"

# ===== KubeRay operator =====
#
# The upstream Helm chart, pinned and in its own namespace. The developer guide
# gives `helm install kuberay-operator kuberay/kuberay-operator` with no
# --version and no --namespace, which resolves to whatever is latest and lands a
# cluster-wide operator in `default`. Both are wrong for anything but a demo.

.PHONY: install-kuberay
install-kuberay:
	@if ! command -v helm >/dev/null; then echo "helm is required"; exit 1; fi
	@echo "context: $$(kubectl config current-context)"
	@echo "installing kuberay-operator $(KUBERAY_VERSION) into namespace $(KUBERAY_NAMESPACE)"
	@# Refuse early if another release already owns the chart's cluster-scoped
	@# RBAC. Checking the ClusterRole's Helm ownership annotation tests the exact
	@# condition that makes a second install fail, so there is nothing to parse.
	@owner=$$(kubectl get clusterrole raycronjob-editor-role \
		-o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-namespace}' 2>/dev/null); \
	name=$$(kubectl get clusterrole raycronjob-editor-role \
		-o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null); \
	if [ -n "$$owner" ] && [ "$$owner" != "$(KUBERAY_NAMESPACE)" ]; then \
		echo "KubeRay is already installed as release $$name in namespace $$owner."; \
		echo "The chart's cluster-scoped RBAC has a single owner, so installing"; \
		echo "into $(KUBERAY_NAMESPACE) as well will be refused by Helm."; \
		echo "Delete your Ray resources, then:  helm uninstall $$name -n $$owner"; \
		exit 1; \
	fi
	helm repo add kuberay https://ray-project.github.io/kuberay-helm/ --force-update
	helm repo update kuberay
	helm upgrade --install $(KUBERAY_RELEASE) kuberay/kuberay-operator \
		--version $(KUBERAY_VERSION) \
		--namespace $(KUBERAY_NAMESPACE) --create-namespace \
		--wait --timeout 10m
	@$(MAKE) --no-print-directory operator-status

.PHONY: uninstall-kuberay
uninstall-kuberay:
	@echo "Uninstalling the operator stops reconciliation of every Ray resource in"
	@echo "the cluster: running Ray clusters keep running but are no longer managed,"
	@echo "and deletions never complete. Delete your Ray resources first."
	@kubectl get rayclusters,rayjobs,rayservices,raycronjobs -A 2>/dev/null || true
	@read -p "Uninstall $(KUBERAY_RELEASE) from $(KUBERAY_NAMESPACE)? [y/N] " ok; [ "$$ok" = "y" ]
	helm uninstall $(KUBERAY_RELEASE) --namespace $(KUBERAY_NAMESPACE)
	@echo "Note: the ray.io CRDs survive on purpose - Helm never deletes crds/."

.PHONY: kuberay-version
kuberay-version:
	@helm list -n $(KUBERAY_NAMESPACE) 2>/dev/null
	@kubectl get deployment $(KUBERAY_RELEASE) -n $(KUBERAY_NAMESPACE) \
		-o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}' 2>/dev/null

# ===== SageMaker AI domain =====

.PHONY: deploy-domain
deploy-domain:
	$(require_cluster)
	@if [ -z "$(HYPERPOD_CLUSTER_NAME)" ]; then \
		echo "Set HYPERPOD_CLUSTER_NAME (the HyperPod cluster, not the EKS cluster)."; \
		exit 1; \
	fi
	@if [ -z "$(DOMAIN_VPC_ID)" ] || [ -z "$(DOMAIN_SUBNET_IDS)" ]; then \
		echo "Set DOMAIN_VPC_ID and DOMAIN_SUBNET_IDS. Find them with:"; \
		echo "  aws eks describe-cluster --name $(EKS_CLUSTER_NAME) --region $(AWS_REGION) \\"; \
		echo "    --query 'cluster.resourcesVpcConfig.{Vpc:vpcId,Subnets:subnetIds}'"; \
		exit 1; \
	fi
	@overrides=( \
		EKSClusterName=$(EKS_CLUSTER_NAME) \
		HyperPodClusterName=$(HYPERPOD_CLUSTER_NAME) \
		DomainName=$(DOMAIN_NAME) \
		UserProfileName=$(USER_PROFILE_NAME) \
		VpcId=$(DOMAIN_VPC_ID) \
		SubnetIds=$(DOMAIN_SUBNET_IDS) \
		AccessScopeNamespaces="$(ACCESS_SCOPE_NAMESPACES)" \
		KubernetesGroups="$(KUBERNETES_GROUPS)" \
		SpaceTemplateNamespaces="$(SPACE_TEMPLATE_NAMESPACES)" \
		AttachTrainingPolicy=$(ATTACH_TRAINING_POLICY) \
		AttachInferencePolicy=$(ATTACH_INFERENCE_POLICY) \
		AttachSpacePolicy=$(ATTACH_SPACE_POLICY) \
		AttachSpaceTemplatePolicy=$(ATTACH_SPACE_TEMPLATE_POLICY) \
		AttachUserClusterPolicy=$(ATTACH_USER_CLUSTER_POLICY) \
	); \
	set -x; \
	$(AWS) cloudformation deploy \
		--template-file $(DOMAIN_TEMPLATE) \
		--stack-name $(DOMAIN_STACK_NAME) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides "$${overrides[@]}"
	@$(MAKE) --no-print-directory domain-outputs

.PHONY: domain-outputs
domain-outputs:
	$(AWS) cloudformation describe-stacks \
		--stack-name $(DOMAIN_STACK_NAME) \
		--query 'Stacks[0].Outputs' --output table

.PHONY: domain-events
domain-events:
	$(AWS) cloudformation describe-stack-events \
		--stack-name $(DOMAIN_STACK_NAME) \
		--query 'reverse(StackEvents[:25].[Timestamp,ResourceStatus,LogicalResourceId,ResourceStatusReason])' \
		--output table

# Proof that cluster access landed, read from EKS rather than from the console.
.PHONY: domain-access
domain-access:
	$(require_cluster)
	@role=$$($(AWS) cloudformation describe-stacks --stack-name $(DOMAIN_STACK_NAME) \
		--query 'Stacks[0].Outputs[?OutputKey==`ExecutionRoleArn`].OutputValue' --output text); \
	$(AWS) eks list-associated-access-policies --cluster-name $(EKS_CLUSTER_NAME) \
		--principal-arn "$$role" --query 'associatedAccessPolicies[].{Policy:policyArn,Scope:accessScope.type,Namespaces:accessScope.namespaces}' \
		--output table

.PHONY: delete-domain
delete-domain:
	@echo "This deletes the SageMaker AI domain, its user profile, and the"
	@echo "cluster access entry. Delete any spaces and apps in the domain first;"
	@echo "a domain with running apps will not delete."
	@read -p "Delete stack $(DOMAIN_STACK_NAME)? [y/N] " ok; [ "$$ok" = "y" ]
	$(AWS) cloudformation delete-stack --stack-name $(DOMAIN_STACK_NAME)
	$(AWS) cloudformation wait stack-delete-complete --stack-name $(DOMAIN_STACK_NAME)

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

# ===== Example workloads =====

# Ray needs the entrypoint script to exist inside the cluster. The three usual ways
# are baking it into an image, uploading it with `ray job submit --working-dir`, or
# mounting it. A ConfigMap is the one that keeps a manifest runnable on its own,
# which is why the examples use it; it caps out at 1 MiB, so real code belongs in
# an image or in runtime_env.working_dir pointing at S3.
.PHONY: examples-configmap
examples-configmap:
	kubectl create configmap $(EXAMPLES_CONFIGMAP) -n $(RAY_NAMESPACE) \
		--from-file=examples/scripts \
		--dry-run=client -o yaml | kubectl apply -f -

.PHONY: run-job
run-job: examples-configmap
	kubectl apply -f examples/rayjob-ephemeral.yaml -n $(RAY_NAMESPACE)
	@echo "Follow it with: make job-logs JOB=ray-data-job"

.PHONY: run-job-existing
run-job-existing: examples-configmap
	kubectl apply -f examples/rayjob-existing.yaml -n $(RAY_NAMESPACE)
	@echo "Follow it with: make job-logs JOB=ray-train-job"

.PHONY: list-jobs
list-jobs:
	kubectl get rayjobs -n $(RAY_NAMESPACE)

# KubeRay runs the entrypoint from a submitter pod, whose Kubernetes Job takes the
# RayJob's name. That pod streams the driver output, so it is the one to read.
.PHONY: job-logs
job-logs:
	kubectl logs -n $(RAY_NAMESPACE) -f --tail=-1 \
		-l batch.kubernetes.io/job-name=$(JOB)

.PHONY: delete-jobs
delete-jobs:
	-kubectl delete -f examples/rayjob-ephemeral.yaml -n $(RAY_NAMESPACE)
	-kubectl delete -f examples/rayjob-existing.yaml -n $(RAY_NAMESPACE)

.PHONY: deploy-service
deploy-service: examples-configmap
	kubectl apply -f examples/rayservice-serve.yaml -n $(RAY_NAMESPACE)
	@echo "Wait for it with: make service-status"

.PHONY: service-status
service-status:
	kubectl get rayservice $(SERVICE_NAME) -n $(RAY_NAMESPACE)

# RayService creates a stable service that points at whichever cluster is currently
# serving, so an upgrade does not change the address a client uses.
.PHONY: service-request
service-request:
	@kubectl port-forward -n $(RAY_NAMESPACE) \
		service/$(SERVICE_NAME)-serve-svc 8000:8000 >/dev/null 2>&1 & \
	forward=$$!; \
	trap "kill $$forward 2>/dev/null" EXIT; \
	sleep 3; \
	curl -sS localhost:8000 -H "Content-Type: application/json" \
		-d '{"values": [1, 2, 10]}'; \
	echo

.PHONY: delete-service
delete-service:
	kubectl delete -f examples/rayservice-serve.yaml -n $(RAY_NAMESPACE)

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
