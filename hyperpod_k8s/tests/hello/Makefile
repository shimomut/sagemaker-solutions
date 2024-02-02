SHELL := /bin/bash

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

# FIXME : this doesn't work in Makefile
secret:
	kubectl create secret docker-registry regcred --docker-server=842413447717.dkr.ecr.us-west-2.amazonaws.com --docker-username=AWS --docker-password=$(aws --region us-west-2 ecr get-login-password) --namespace=myhello

deploy:
	kubectl apply -f deployment.yaml

