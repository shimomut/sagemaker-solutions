SHELL := /bin/bash

all:

build:
	docker build --tag myhello .

local-run:
	docker run myhello

login:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-west-2.amazonaws.com

tag:
	docker tag myhello:latest 842413447717.dkr.ecr.us-west-2.amazonaws.com/myhello:latest

push:
	docker push 842413447717.dkr.ecr.us-west-2.amazonaws.com/myhello:latest

# ---

namespace:
	kubectl create namespace myhello

secret:
	kubectl create secret docker-registry regcred --docker-server=842413447717.dkr.ecr.us-west-2.amazonaws.com --docker-username=AWS --docker-password=$$(aws --region us-west-2 ecr get-login-password) --namespace=myhello

deploy:
	kubectl apply -f deployment.yaml

delete:
	kubectl delete deployment hello-deployment -n myhello

list-pods:
	kubectl get pods -n myhello -o wide

# ---

containerd-config:
	sudo vi /etc/containerd/config.toml
	sudo systemctl restart containerd.service
