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

DEPLOY_DIR   := deploy
STACK_NAME   ?= hyperpod-devops-agent

.PHONY: help venv extract-docs \
        config check-aws check-cluster \
        deploy update teardown-stack \
        sync-skills stack-status stack-outputs \
        bridge-logs2 audit-logs2 email-logs2 audit-test2 \
        setup foundation provision-webhook eks-access \
        webhook-secret deploy-bridge delete-bridge bridge-logs bridge-test \
        bridge-debug-on bridge-debug-off bridge-env \
        upload-skill list-skills delete-skill import-upstream-skills \
        deploy-periodic-audit delete-periodic-audit audit-logs audit-test \
        deploy-email-notifier delete-email-notifier email-notifier-logs \
        teardown status clean

help:
	@echo "Unified single-stack deployment (deploy/template.yaml) — recommended:"
	@echo "  deploy        - One command: sync skills, embed Lambdas, deploy the whole stack."
	@echo "                  Reads deploy/params.json (copy from params.example.json)."
	@echo "  update        - Alias for deploy (idempotent; re-uploads changed skills)."
	@echo "  sync-skills   - Zip skills + mental-model doc, upload to the S3 assets bucket."
	@echo "  stack-status  - Show the unified stack status."
	@echo "  stack-outputs - Show the unified stack outputs (console URL, secret ARN, ...)."
	@echo "  teardown-stack- Delete the unified stack + assets bucket (CRs self-clean first)."
	@echo "  bridge-logs2 / audit-logs2 / email-logs2 - Tail a Lambda's logs (unified stack)."
	@echo "  audit-test2   - Manually invoke the periodic-audit Lambda once (unified stack)."
	@echo
	@echo "Legacy per-component targets (kept until the unified path is validated):"
	@echo
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
	@echo "  foundation        - Deploy CFN stack: IAM roles + AgentSpace + AWS monitor association"
	@echo "  provision-webhook - Register eventChannel service + associate to Agent Space"
	@echo "                      (imperative — CFN doesn't yet expose the webhook URL/HMAC)"
	@echo "  eks-access        - Grant the monitoring role read-only access to the EKS cluster"
	@echo "  setup             - foundation -> provision-webhook -> eks-access"
	@echo
	@echo "Periodic audit (Goal 1: monitor open incidents + Resolved closure):"
	@echo "  deploy-periodic-audit - Deploy CFN stack: EB Scheduler + Lambda that fires the"
	@echo "                          hyperpod-incident-rca skill in audit mode every 15 min."
	@echo "                          (DevOps Agent's native scheduled triggers don't support"
	@echo "                          full investigation tasks — see Goal 1 in the README.)"
	@echo "  delete-periodic-audit - Delete the periodic-audit stack"
	@echo "  audit-logs            - Tail the audit Lambda's CloudWatch Logs"
	@echo "  audit-test            - Manually invoke the audit Lambda once"
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
	@echo "  upload-skill    - Zip a skill directory and create or update the asset"
	@echo "                    (SKILL_DIR=skills/my-skill required)"
	@echo "  list-skills     - Show every skill asset in the Agent Space"
	@echo "  delete-skill    - Delete a skill by name"
	@echo "                    (SKILL_NAME=... or SKILL_DIR=... to identify the skill)"
	@echo "  import-upstream-skills - Clone awslabs/agent-plugins, strip scripts/, upload"
	@echo "                           every hyperpod-* skill (SKILLS='name1 name2' to subset)"
	@echo
	@echo "Email notifications (DevOps Agent investigations -> SES email):"
	@echo "  deploy-email-notifier  - Deploy EventBridge rule + Lambda + SES sender"
	@echo "                           (EMAIL_SENDER=... EMAIL_RECIPIENTS=... required)"
	@echo "  delete-email-notifier  - Delete the email notifier stack"
	@echo "  email-notifier-logs    - Tail the email notifier Lambda's CloudWatch Logs"
	@echo
	@echo "Operate / teardown:"
	@echo "  status        - Print state file + console URL for the Agent Space"
	@echo "  teardown      - Reverse setup (EKS entry, agent space, IAM roles)"
	@echo "  clean         - Remove venv and extracted .txt files (no AWS calls)"

# ------------------------------------------------------------ unified single-stack deployment

deploy:
	STACK_NAME=$(STACK_NAME) bash $(DEPLOY_DIR)/deploy.sh

update: deploy

sync-skills:
	@bash -c 'set -euo pipefail; \
		REGION=$${REGION:-$$(aws configure get region)}; \
		ACCOUNT_ID=$$(aws sts get-caller-identity --query Account --output text); \
		BUCKET=hyperpod-devops-agent-assets-$$ACCOUNT_ID-$$REGION; \
		if ! aws s3api head-bucket --bucket $$BUCKET --region $$REGION 2>/dev/null; then \
			if [ "$$REGION" = "us-east-1" ]; then \
				aws s3api create-bucket --bucket $$BUCKET --region $$REGION >/dev/null; \
			else \
				aws s3api create-bucket --bucket $$BUCKET --region $$REGION \
					--create-bucket-configuration LocationConstraint=$$REGION >/dev/null; \
			fi; \
		fi; \
		$(PYTHON3) $(DEPLOY_DIR)/build.py sync-skills --bucket $$BUCKET --region $$REGION'

teardown-stack:
	STACK_NAME=$(STACK_NAME) bash $(DEPLOY_DIR)/teardown.sh

stack-status:
	@bash -c 'REGION=$${REGION:-$$(aws configure get region)}; \
		aws cloudformation describe-stacks --region $$REGION --stack-name $(STACK_NAME) \
			--query "Stacks[0].StackStatus" --output text'

stack-outputs:
	@bash -c 'REGION=$${REGION:-$$(aws configure get region)}; \
		aws cloudformation describe-stacks --region $$REGION --stack-name $(STACK_NAME) \
			--query "Stacks[0].Outputs" --output table'

# Tail a Lambda's logs by reading its function name from a stack output.
# $(1) = output key
define TAIL_STACK_LAMBDA
	@bash -c 'REGION=$${REGION:-$$(aws configure get region)}; \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION --stack-name $(STACK_NAME) \
			--query "Stacks[0].Outputs[?OutputKey=='"'"'$(1)'"'"'].OutputValue | [0]" --output text); \
		if [ -z "$$FUNC" ] || [ "$$FUNC" = "None" ]; then echo "No $(1) in stack outputs."; exit 1; fi; \
		aws logs tail /aws/lambda/$$FUNC --region $$REGION --follow --since 1h'
endef

bridge-logs2:
	$(call TAIL_STACK_LAMBDA,WebhookBridgeFunctionName)

audit-logs2:
	$(call TAIL_STACK_LAMBDA,PeriodicAuditFunctionName)

email-logs2:
	$(call TAIL_STACK_LAMBDA,EmailNotifierFunctionName)

audit-test2:
	@bash -c 'REGION=$${REGION:-$$(aws configure get region)}; \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION --stack-name $(STACK_NAME) \
			--query "Stacks[0].Outputs[?OutputKey=='"'"'PeriodicAuditFunctionName'"'"'].OutputValue | [0]" --output text); \
		if [ -z "$$FUNC" ] || [ "$$FUNC" = "None" ]; then echo "Periodic audit not enabled in this stack."; exit 1; fi; \
		echo "Invoking $$FUNC..."; \
		aws lambda invoke --region $$REGION --function-name $$FUNC --payload "{}" /tmp/audit-test2-output.json \
			--cli-binary-format raw-in-base64-out >/dev/null && cat /tmp/audit-test2-output.json && echo'

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

foundation:
	bash $(SCRIPTS_DIR)/01_deploy_foundation.sh

provision-webhook:
	bash $(SCRIPTS_DIR)/02_provision_webhook.sh

eks-access:
	bash $(SCRIPTS_DIR)/03_grant_eks_access.sh

setup: foundation provision-webhook eks-access

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

# ------------------------------------------------------------ periodic audit (EB Scheduler -> Lambda -> webhook)

deploy-periodic-audit:
	bash $(SCRIPTS_DIR)/12_deploy_periodic_audit.sh

delete-periodic-audit:
	bash $(SCRIPTS_DIR)/13_delete_periodic_audit.sh

audit-logs:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION \
			--stack-name hyperpod-devops-agent-periodic-audit \
			--query "Stacks[0].Outputs[?OutputKey=='\''LambdaFunctionName'\''].OutputValue | [0]" \
			--output text); \
		if [ -z "$$FUNC" ] || [ "$$FUNC" = "None" ]; then \
			echo "Periodic-audit stack not deployed."; exit 1; \
		fi; \
		aws logs tail /aws/lambda/$$FUNC --region $$REGION --follow --since 1h'

audit-test:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION \
			--stack-name hyperpod-devops-agent-periodic-audit \
			--query "Stacks[0].Outputs[?OutputKey=='\''LambdaFunctionName'\''].OutputValue | [0]" \
			--output text); \
		if [ -z "$$FUNC" ] || [ "$$FUNC" = "None" ]; then \
			echo "Periodic-audit stack not deployed."; exit 1; \
		fi; \
		echo "Manually invoking audit Lambda $$FUNC..."; \
		aws lambda invoke --region $$REGION --function-name $$FUNC --payload "{}" /tmp/audit-test-output.json --cli-binary-format raw-in-base64-out >/dev/null && cat /tmp/audit-test-output.json && echo'

# ------------------------------------------------------------ email notifier

deploy-email-notifier:
	bash $(SCRIPTS_DIR)/10_deploy_email_notifier.sh

delete-email-notifier:
	bash $(SCRIPTS_DIR)/11_delete_email_notifier.sh

email-notifier-logs:
	@bash -c 'source $(SCRIPTS_DIR)/config.sh && \
		FUNC=$$(aws cloudformation describe-stacks --region $$REGION \
			--stack-name hyperpod-devops-agent-email-notifier \
			--query "Stacks[0].Outputs[?OutputKey=='\''LambdaFunctionName'\''].OutputValue | [0]" \
			--output text); \
		if [ -z "$$FUNC" ] || [ "$$FUNC" = "None" ]; then \
			echo "Email notifier stack not deployed."; exit 1; \
		fi; \
		aws logs tail /aws/lambda/$$FUNC --region $$REGION --follow --since 1h'

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
