SHELL := /bin/bash

ECR_REPO := 842413447717.dkr.ecr.us-west-2.amazonaws.com/hyperpod-eks-vllm

all:

build:
	docker build --tag hyperpod-eks-vllm .

login:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-west-2.amazonaws.com

tag:
	docker tag hyperpod-eks-vllm:latest $(ECR_REPO):latest

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
