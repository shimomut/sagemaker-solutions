# HyperPod x AWS DevOps Agent — experiment scaffolding
#
# Targets fall into three groups:
#   1. Documentation tooling (venv, extract-docs) - reads the PDFs into .txt.
#   2. Agent Space setup    - IAM roles, Agent Space, EKS access entry.
#   3. Webhook bridge       - Secrets Manager secret + CloudFormation stack
#                              that forwards HyperPod events to the webhook.
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
        webhook-secret deploy-bridge delete-bridge bridge-logs bridge-test \
        bridge-debug-on bridge-debug-off bridge-env \
        upload-skill list-skills delete-skill import-upstream-skills \
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
	@echo "Agent Space setup (run in order, or all at once with 'make setup'):"
	@echo "  iam-roles     - Create DevOps Agent and Webapp IAM roles"
	@echo "  agent-space   - Create Agent Space, associate account, enable operator app"
	@echo "  eks-access    - Grant the monitoring role read-only access to the EKS cluster"
	@echo "  setup         - iam-roles -> agent-space -> eks-access"
	@echo
	@echo "Webhook bridge (after generating webhook URL+secret in the console):"
	@echo "  webhook-secret  - Store webhook URL+secret in Secrets Manager"
	@echo "                    (WEBHOOK_URL=... WEBHOOK_HMAC_SECRET=... make webhook-secret)"
	@echo "  deploy-bridge   - Deploy CloudFormation stack (EventBridge rule + Lambda)"
	@echo "  bridge-test     - Send a synthetic HyperPod event to the real webhook"
	@echo "                    (LOCAL_EVENT_TYPE=node-health|cluster-state-change|cluster-event)"
	@echo "  bridge-logs     - Tail the webhook bridge Lambda's CloudWatch Logs"
	@echo "  delete-bridge   - Delete the CloudFormation stack"
	@echo "                    (DELETE_SECRET=yes also removes the Secrets Manager entry)"
	@echo "  bridge-debug-on  - Turn on full-event + outgoing-payload logging on the Lambda"
	@echo "                     (DRY_RUN=yes also skips the actual webhook POST)"
	@echo "  bridge-debug-off - Restore normal logging on the Lambda"
	@echo "  bridge-env       - Show the Lambda's current env vars"
	@echo
	@echo "Skill management (uploads SKILL.md + references to the Agent Space):"
	@echo "  upload-skill    - Zip skills/hyperpod-investigation/ and create or update the asset"
	@echo "                    (SKILL_DIR=skills/other to upload a different skill)"
	@echo "  list-skills     - Show every skill asset in the Agent Space"
	@echo "  delete-skill    - Delete the skill named in SKILL.md's frontmatter"
	@echo "                    (SKILL_DIR=... or SKILL_NAME=... to target a specific skill)"
	@echo "  import-upstream-skills - Clone awslabs/agent-plugins, strip scripts/, upload"
	@echo "                           every hyperpod-* skill (SKILLS='name1 name2' to subset)"
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

# ------------------------------------------------------------ Agent Space setup

iam-roles:
	bash $(SCRIPTS_DIR)/01_create_iam_roles.sh

agent-space:
	bash $(SCRIPTS_DIR)/02_create_agent_space.sh

eks-access:
	bash $(SCRIPTS_DIR)/03_grant_eks_access.sh

setup: iam-roles agent-space eks-access

# ------------------------------------------------------------ webhook bridge

webhook-secret:
	bash $(SCRIPTS_DIR)/04_create_webhook_secret.sh

deploy-bridge:
	bash $(SCRIPTS_DIR)/05_deploy_webhook_bridge.sh

delete-bridge:
	bash $(SCRIPTS_DIR)/06_delete_webhook_bridge.sh

bridge-debug-on:
	bash $(SCRIPTS_DIR)/bridge_debug.sh on $(DRY_RUN)

bridge-debug-off:
	bash $(SCRIPTS_DIR)/bridge_debug.sh off

bridge-env:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION \
			--stack-name hyperpod-devops-agent-webhook-bridge \
			--query "Stacks[0].Outputs[?OutputKey=='\''LambdaFunctionName'\''].OutputValue | [0]" \
			--output text); \
		aws lambda get-function-configuration --region $$REGION --function-name $$FUNC \
			--query "Environment.Variables" --output table'

bridge-test: venv
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		EVENT_TYPE=$${LOCAL_EVENT_TYPE:-node-health}; \
		$(VENV_PYTHON) webhook_bridge/local_test.py --event-type $$EVENT_TYPE --region $$REGION'

bridge-logs:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION \
			--stack-name hyperpod-devops-agent-webhook-bridge \
			--query "Stacks[0].Outputs[?OutputKey=='\''LambdaFunctionName'\''].OutputValue | [0]" \
			--output text); \
		if [ -z "$$FUNC" ] || [ "$$FUNC" = "None" ]; then \
			echo "Stack not deployed."; exit 1; \
		fi; \
		aws logs tail /aws/lambda/$$FUNC --region $$REGION --follow --since 1h'

# ------------------------------------------------------------ skill management

upload-skill:
	bash $(SCRIPTS_DIR)/07_upload_skill.sh

delete-skill:
	bash $(SCRIPTS_DIR)/08_delete_skill.sh

import-upstream-skills:
	bash $(SCRIPTS_DIR)/09_import_upstream_skills.sh

list-skills:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		ID=$$($(PYTHON3) -c "import json; print(json.load(open(\".state.json\")).get(\"agentSpaceId\",\"\"))" ); \
		if [ -z "$$ID" ]; then echo "No agentSpaceId in .state.json"; exit 1; fi; \
		aws devops-agent list-assets --region $$REGION --agent-space-id $$ID --max-results 50 \
			--query "items[?assetType==\`skill\`].{assetId:assetId,name:metadata.name,version:version,status:metadata.status,type:metadata.skill_type}" \
			--output table'

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
	rm -f webhook_bridge/template.embedded.yaml
