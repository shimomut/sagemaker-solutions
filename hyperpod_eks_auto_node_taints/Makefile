SHELL := /bin/bash

build:
	docker build --tag mutating-webhook .

local-run:
	docker run -v ./certs:/certs mutating-webhook

login:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-west-2.amazonaws.com

tag:
	docker tag mutating-webhook:latest 842413447717.dkr.ecr.us-west-2.amazonaws.com/mutating-webhook:latest

push:
	docker push 842413447717.dkr.ecr.us-west-2.amazonaws.com/mutating-webhook:latest

# ---

deploy-webhook:
	kubectl apply -f webhook.yaml -n auto-node-taints-test

delete-webhook:
	kubectl delete -f webhook.yaml -n auto-node-taints-test

watch-webhook-logs:
	kubectl logs -f -l app=mutating-webhook -n auto-node-taints-test

list-webhook-pods:
	kubectl get pods -o wide -n auto-node-taints-test

# ---

deploy-hello:
	kubectl apply -f hello.yaml

delete-hello:
	kubectl delete -f hello.yaml

# ---

list-nodes:
	kubectl get nodes "-o=custom-columns=NAME:.metadata.name,CREATION_TIME:.metadata.creationTimestamp,HEALTH:.metadata.labels.sagemaker\.amazonaws\.com/node-health-status,DHC:.metadata.labels.sagemaker\.amazonaws\.com\/deep-health-check-status,TAINTS:.spec.taints"

delete-taints:
	kubectl taint nodes --all mutating-webhook-taint-
