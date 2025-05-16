SHELL := /bin/bash

POD_NAME ?= POD_NAME
PID ?= 1
PORT_NUMBER ?= 5678

all:

local-run:
	python debug_target.py

local-attach:
	python -m pdb_attach $(PID) $(PORT_NUMBER)

# ---

build:
	docker build --tag debug-target .

login:
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-east-1.amazonaws.com

tag:
	docker tag debug-target:latest 842413447717.dkr.ecr.us-east-1.amazonaws.com/debug-target:latest

push:
	docker push 842413447717.dkr.ecr.us-east-1.amazonaws.com/debug-target:latest

# ---

deploy:
	kubectl apply -f deployment.yaml

delete:
	kubectl delete -f deployment.yaml

watch-logs-all:
	kubectl logs -f -l app=debug-target --max-log-requests=300	

list-pods:
	kubectl get pods -o wide

exec-bash:
	kubectl exec -it $(POD_NAME) -- bash
