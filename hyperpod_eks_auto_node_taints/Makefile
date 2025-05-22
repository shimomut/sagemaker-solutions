SHELL := /bin/bash

build-image:
	docker build --tag mutating-webhook .

local-run-image:
	docker run -v ./certs:/certs mutating-webhook

login-ecr:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-west-2.amazonaws.com

tag-image:
	docker tag mutating-webhook:latest 842413447717.dkr.ecr.us-west-2.amazonaws.com/mutating-webhook:latest

push-image:
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

deploy-webhook-config:
	kubectl apply -f mutating_webhook_config.yaml

delete-webhook-config:
	kubectl delete -f mutating_webhook_config.yaml

list-webhook-config:
	kubectl get MutatingWebhookConfiguration	

# ---

list-nodes:
	kubectl get nodes "-o=custom-columns=NAME:.metadata.name,CREATION_TIME:.metadata.creationTimestamp,HEALTH:.metadata.labels.sagemaker\.amazonaws\.com/node-health-status,DHC:.metadata.labels.sagemaker\.amazonaws\.com\/deep-health-check-status,TAINTS:.spec.taints"

list-hyperpod-pods:
	kubectl get pods -n aws-hyperpod -o custom-columns=\
	NAME:.metadata.name,\
	READY:.status.containerStatuses[0].ready,\
	STATUS:.status.phase,\
	RESTARTS:.status.containerStatuses[0].restartCount,\
	AGE:.metadata.creationTimestamp,\
	NODE:.spec.nodeName,\
	TOLERATIONS:.spec.tolerations[*].key

manual-delete-taints:
	kubectl taint nodes --all mutating-webhook-taint-
