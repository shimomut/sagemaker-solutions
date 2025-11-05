IMAGE_NAME=shell-tools

create-ecr-repo:
	aws ecr create-repository --repository-name ${IMAGE_NAME} --region ${REGION} || true

build:
	docker build --tag ${IMAGE_NAME} .

login:
	aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com

tag:
	docker tag ${IMAGE_NAME}:latest ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:latest

push:
	docker push ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:latest

deploy-shell:
	SHELL_IMAGE=${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:latest envsubst < shell-pod.yaml | kubectl apply -f -

deploy-shell-default:
	SHELL_IMAGE=ubuntu:22.04 envsubst < shell-pod.yaml | kubectl apply -f -

shell:
	kubectl exec -it shell -- bash

delete-shell:
	kubectl delete pod shell

all: create-ecr-repo build login tag push