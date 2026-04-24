SHELL := /bin/bash

AWS_ACCOUNT_ID := 842413447717
AWS_REGION := us-west-2
IMAGE_NAME := hyperpod-eks-vllm-advanced
ECR_REPO := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME)

PROMPT ?= What is machine learning?

.PHONY: all venv build login tag push deploy delete list-pods watch-logs get-endpoint \
	deploy-alb delete-alb deploy-ray delete-ray deploy-redis delete-redis \
	deploy-monitoring delete-monitoring deploy-hpa delete-hpa \
	deploy-disaggregated delete-disaggregated \
	test-inference benchmark port-forward port-forward-grafana \
	deploy-all delete-all

all:

# ──────────────────────────────────────────────
# Virtual Environment
# ──────────────────────────────────────────────

venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

# ──────────────────────────────────────────────
# Build Targets
# ──────────────────────────────────────────────

build:
	docker build --platform linux/amd64 --tag $(IMAGE_NAME) .

login:
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

tag:
	docker tag $(IMAGE_NAME):latest $(ECR_REPO):latest

push:
	docker push $(ECR_REPO):latest

# ──────────────────────────────────────────────
# Core Targets
# ──────────────────────────────────────────────

deploy:
	kubectl apply -f manifests/vllm-deployment.yaml
	kubectl apply -f manifests/vllm-service.yaml

delete:
	kubectl delete -f manifests/vllm-service.yaml --ignore-not-found
	kubectl delete -f manifests/vllm-deployment.yaml --ignore-not-found

list-pods:
	kubectl get pods -l app=vllm-advanced-server -o wide

watch-logs:
	kubectl logs -f -l app=vllm-advanced-server

get-endpoint:
	@echo "--- NodePort ---"
	kubectl get svc vllm-advanced-server -o jsonpath='{.spec.clusterIP}:{.spec.ports[0].port}'; echo
	@echo "--- ALB (if deployed) ---"
	-kubectl get ingress vllm-advanced-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'; echo

# ──────────────────────────────────────────────
# Per-Feature Targets
# ──────────────────────────────────────────────

deploy-alb:
	kubectl apply -f manifests/alb-ingress.yaml

delete-alb:
	kubectl delete -f manifests/alb-ingress.yaml --ignore-not-found

deploy-ray:
	kubectl apply -f manifests/ray-cluster.yaml

delete-ray:
	kubectl delete -f manifests/ray-cluster.yaml --ignore-not-found

deploy-redis:
	kubectl apply -f manifests/redis.yaml

delete-redis:
	kubectl delete -f manifests/redis.yaml --ignore-not-found

deploy-monitoring:
	kubectl apply -f manifests/prometheus.yaml
	kubectl apply -f manifests/grafana.yaml

delete-monitoring:
	kubectl delete -f manifests/grafana.yaml --ignore-not-found
	kubectl delete -f manifests/prometheus.yaml --ignore-not-found

deploy-hpa:
	kubectl apply -f manifests/prometheus-adapter.yaml
	kubectl apply -f manifests/hpa.yaml

delete-hpa:
	kubectl delete -f manifests/hpa.yaml --ignore-not-found
	kubectl delete -f manifests/prometheus-adapter.yaml --ignore-not-found

deploy-disaggregated:
	kubectl apply -f manifests/disaggregated-serving.yaml

delete-disaggregated:
	kubectl delete -f manifests/disaggregated-serving.yaml --ignore-not-found

# ──────────────────────────────────────────────
# Test Targets
# ──────────────────────────────────────────────

test-inference:
	.venv/bin/python client.py "$(PROMPT)"

benchmark:
	.venv/bin/python benchmark.py

# ──────────────────────────────────────────────
# Utility Targets
# ──────────────────────────────────────────────

port-forward:
	kubectl port-forward svc/vllm-advanced-server 8000:8000

port-forward-grafana:
	kubectl port-forward svc/grafana 3000:3000

deploy-all: deploy deploy-alb deploy-ray deploy-redis deploy-monitoring deploy-hpa deploy-disaggregated

delete-all: delete-disaggregated delete-hpa delete-monitoring delete-redis delete-ray delete-alb delete
