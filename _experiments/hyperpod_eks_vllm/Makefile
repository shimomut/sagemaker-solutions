SHELL := /bin/bash

AWS_ACCOUNT_ID := 842413447717
AWS_REGION := us-west-2
IMAGE_NAME := hyperpod-eks-vllm
ECR_REPO := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME)

all:

build:
	docker build --platform linux/amd64 --tag $(IMAGE_NAME) .

create-repo:
	aws ecr create-repository --repository-name $(IMAGE_NAME) --region $(AWS_REGION)

login:
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

tag:
	docker tag $(IMAGE_NAME):latest $(ECR_REPO):latest

push:
	docker push $(ECR_REPO):latest

deploy:
	kubectl apply -f deployment.yaml

delete:
	kubectl delete -f deployment.yaml

list-pods:
	kubectl get pods -l app=vllm-server -o wide

watch-logs:
	kubectl logs -f -l app=vllm-server

port-forward:
	kubectl port-forward svc/vllm-server 8000:8000
