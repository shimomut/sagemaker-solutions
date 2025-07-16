SHELL := /bin/bash

all:

build:
	docker build --tag emptydir-test .

local-run:
	docker run emptydir-test

login:
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-east-1.amazonaws.com

tag:
	docker tag emptydir-test:latest 842413447717.dkr.ecr.us-east-1.amazonaws.com/emptydir-test:latest

push:
	docker push 842413447717.dkr.ecr.us-east-1.amazonaws.com/emptydir-test:latest

# ---

deploy:
	kubectl apply -f deployment.yaml

delete:
	kubectl delete -f deployment.yaml

watch-logs-all:
	kubectl logs -f -l app=emptydir-test --max-log-requests=300	

list-pods:
	kubectl get pods -o wide

