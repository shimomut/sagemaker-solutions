# HyperPod x AWS DevOps Agent — experiment scaffolding
#
# Targets fall into two groups:
#   1. Documentation tooling (venv, extract-docs) - reads the PDFs into .txt.
#   2. PoC setup/teardown   - sets up an Agent Space monitoring cluster k8-1.
#
# All AWS-touching targets call bash scripts under scripts/. The scripts read
# scripts/config.sh which honors REGION, HYPERPOD_CLUSTER_NAME, EKS_CLUSTER_NAME,
# AGENT_SPACE_NAME and a few other env overrides.

PYTHON3 ?= python3

VENV_DIR    := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP    := $(VENV_DIR)/bin/pip
VENV_STAMP  := $(VENV_DIR)/.installed

DOCS_DIR := docs
PDFS     := $(wildcard $(DOCS_DIR)/*.pdf)
TXTS     := $(PDFS:.pdf=.txt)

SCRIPTS_DIR := scripts

.PHONY: help venv extract-docs \
        config check-aws check-cluster \
        setup iam-roles agent-space eks-access \
        teardown status clean

help:
	@echo "Documentation tooling:"
	@echo "  venv          - Create local virtualenv and install pypdf"
	@echo "  extract-docs  - Extract docs/*.pdf to docs/*.txt for grep"
	@echo
	@echo "Pre-flight:"
	@echo "  config        - Show resolved configuration"
	@echo "  check-aws     - Verify AWS credentials are usable"
	@echo "  check-cluster - Verify HyperPod cluster and underlying EKS auth mode"
	@echo
	@echo "PoC setup (run in order, or all at once with 'make setup'):"
	@echo "  iam-roles     - Create DevOps Agent and Webapp IAM roles"
	@echo "  agent-space   - Create Agent Space, associate account, enable operator app"
	@echo "  eks-access    - Grant the monitoring role read-only access to the EKS cluster"
	@echo "  setup         - iam-roles -> agent-space -> eks-access"
	@echo
	@echo "Operate / teardown:"
	@echo "  status        - Print state file + console URL for the Agent Space"
	@echo "  teardown      - Reverse setup (EKS entry, agent space, IAM roles)"
	@echo "  clean         - Remove venv and extracted .txt files (no AWS calls)"

# ------------------------------------------------------------ docs tooling

venv: $(VENV_STAMP)

$(VENV_STAMP): requirements.txt
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Creating venv at $(VENV_DIR) using $(PYTHON3)..."; \
		$(PYTHON3) -m venv $(VENV_DIR); \
	fi
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	@touch $(VENV_STAMP)

extract-docs: venv
	@if [ -z "$(PDFS)" ]; then \
		echo "No PDFs found under $(DOCS_DIR)/"; \
		exit 0; \
	fi
	$(VENV_PYTHON) extract_pdf.py $(PDFS)

# ------------------------------------------------------------ pre-flight

config:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && print_config'

check-aws:
	@aws sts get-caller-identity

check-cluster:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		aws sagemaker describe-cluster --cluster-name $$HYPERPOD_CLUSTER_NAME --region $$REGION \
			--query "{Name:ClusterName,Status:ClusterStatus,EKS:Orchestrator.Eks.ClusterArn}" && \
		aws eks describe-cluster --name $$EKS_CLUSTER_NAME --region $$REGION \
			--query "cluster.{AuthMode:accessConfig.authenticationMode,Status:status}"'

# ------------------------------------------------------------ setup steps

iam-roles:
	bash $(SCRIPTS_DIR)/01_create_iam_roles.sh

agent-space:
	bash $(SCRIPTS_DIR)/02_create_agent_space.sh

eks-access:
	bash $(SCRIPTS_DIR)/03_grant_eks_access.sh

setup: iam-roles agent-space eks-access

# ------------------------------------------------------------ operate / teardown

status:
	@if [ ! -f .state.json ]; then \
		echo "No .state.json yet. Run 'make setup' first."; \
		exit 0; \
	fi
	@cat .state.json
	@echo
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		ID=$$($(PYTHON3) -c "import json; print(json.load(open(\".state.json\")).get(\"agentSpaceId\",\"\"))" ); \
		if [ -n "$$ID" ]; then \
			echo "Console: https://$$REGION.console.aws.amazon.com/aidevops/home?region=$$REGION#/agentspaces/$$ID"; \
		fi'

teardown:
	bash $(SCRIPTS_DIR)/99_teardown.sh

clean:
	rm -rf $(VENV_DIR)
	rm -f $(TXTS)
