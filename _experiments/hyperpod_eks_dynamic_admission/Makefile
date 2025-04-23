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

deploy:
	kubectl apply -f deployment.yaml -n mynamespace

delete:
	kubectl delete -f deployment.yaml -n mynamespace

watch-logs-all:
	kubectl logs -f -l app=mywebhook -n mynamespace

list-pods:
	kubectl get pods -o wide -n mynamespace

