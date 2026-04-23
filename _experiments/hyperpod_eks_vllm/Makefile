SHELL := /bin/bash

AWS_ACCOUNT_ID := 842413447717
AWS_REGION := us-west-2
IMAGE_NAME := hyperpod-eks-vllm
ECR_REPO := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME)

all:

venv:
	python3.14 -m venv .venv
	.venv/bin/pip install -r requirements.txt

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

create-secret:
	kubectl create secret generic hf-token --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -

create-env:
	@if [ -f .env ]; then echo ".env already exists"; exit 1; fi
	@read -p "Enter your Hugging Face token: " token; \
	echo "HUGGING_FACE_HUB_TOKEN=$$token" > .env; \
	echo ".env created"

delete-secret:
	kubectl delete secret hf-token --ignore-not-found

check-secret:
	kubectl get secret hf-token -o jsonpath='{.data.HUGGING_FACE_HUB_TOKEN}' | base64 --decode; echo

delete:
	kubectl delete -f deployment.yaml

list-pods:
	kubectl get pods -l app=vllm-server -o wide

watch-logs:
	kubectl logs -f -l app=vllm-server

port-forward:
	kubectl port-forward svc/vllm-server 8000:8000

PROMPT ?= What is machine learning?

test-inference:
	.venv/bin/python client.py "$(PROMPT)"
