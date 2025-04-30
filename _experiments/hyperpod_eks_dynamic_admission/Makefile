SHELL := /bin/bash

all:

build:
	docker build --tag webhook .

local-run:
	docker run -v ./certs:/certs webhook

login:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-west-2.amazonaws.com

tag:
	docker tag webhook:latest 842413447717.dkr.ecr.us-west-2.amazonaws.com/webhook:latest

push:
	docker push 842413447717.dkr.ecr.us-west-2.amazonaws.com/webhook:latest

# ---

deploy-webhook:
	kubectl apply -f webhook.yaml -n mynamespace

delete-webhook:
	kubectl delete -f webhook.yaml -n mynamespace

watch-webhook-logs:
	kubectl logs -f -l app=mywebhook -n mynamespace

list-webhook-pods:
	kubectl get pods -o wide -n mynamespace

# ---

deploy-hello:
	kubectl apply -f hello.yaml

delete-hello:
	kubectl delete -f hello.yaml
