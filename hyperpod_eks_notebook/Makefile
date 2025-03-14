SHELL := /bin/bash

all:

build:
	docker build --tag notebook .

local-run:
	docker run notebook

login:
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-east-1.amazonaws.com

tag:
	docker tag notebook:latest 842413447717.dkr.ecr.us-east-1.amazonaws.com/notebook:latest

push:
	docker push 842413447717.dkr.ecr.us-east-1.amazonaws.com/notebook:latest

# ---

deploy:
	kubectl apply -f deployment.yaml

delete:
	kubectl delete -f deployment.yaml

watch-logs-all:
	kubectl logs -f -l app=notebook --max-log-requests=300	

list-pods:
	kubectl get pods -o wide

port-forward: # on local machine
	kubectl port-forward service/notebook-service 8888:8888

open-browser: # on local machine
	open http://127.0.0.1:8888
