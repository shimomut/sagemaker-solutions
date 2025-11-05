IMAGE_NAME=shell-tools

# Check required environment variables
check-env:
	@echo "Checking required environment variables..."
	@if [ -z "$(REGION)" ]; then \
		echo "Error: REGION environment variable is not set"; \
		echo "Please set it with: export REGION=your-region"; \
		exit 1; \
	fi
	@if [ -z "$(ACCOUNT)" ]; then \
		echo "Error: ACCOUNT environment variable is not set"; \
		echo "Please set it with: export ACCOUNT=your-account-id"; \
		exit 1; \
	fi
	@echo "Environment variables are set: REGION=$(REGION), ACCOUNT=$(ACCOUNT)"

create-ecr-repo: check-env
	aws ecr create-repository --repository-name ${IMAGE_NAME} --region ${REGION} || true

build:
	docker build --tag ${IMAGE_NAME} .

login: check-env
	aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com

tag: check-env
	docker tag ${IMAGE_NAME}:latest ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:latest

push: check-env
	docker push ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:latest

deploy-shell: check-env
	SHELL_IMAGE=${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:latest envsubst < shell-pod.yaml | kubectl apply -f -

deploy-shell-default:
	SHELL_IMAGE=ubuntu:22.04 envsubst < shell-pod.yaml | kubectl apply -f -

shell:
	kubectl exec -it shell -- bash

delete-shell:
	kubectl delete pod shell

all: create-ecr-repo build login tag push