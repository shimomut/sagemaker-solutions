SHELL := /bin/bash

all:

upload-lcc:
	aws s3 sync lcc/ s3://sagemaker-cluster-842413447717/lcc/k8s/

install-helm:
	curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 \
		&& chmod 700 get_helm.sh \
		&& ./get_helm.sh

add-nvidia-helm-repo:
	helm repo add nvidia https://helm.ngc.nvidia.com/nvidia \
		&& helm repo update

install-gpu-operator:
	helm install --wait --generate-name \
		-n gpu-operator --create-namespace \
		nvidia/gpu-operator \
		--set driver.enabled=false

login-efa-device-plugin-reg:
	kubectl create secret docker-registry regcred-efa --docker-server=602401143452.dkr.ecr.us-west-2.amazonaws.com --docker-username=AWS --docker-password=$$(aws --region us-west-2 ecr get-login-password) --namespace=kube-system

install-efa-device-plugin:
	kubectl apply -f efa-k8s-device-plugin.yaml

login-nccl-test:
	kubectl create secret docker-registry regcred-nccl-test --docker-server=842413447717.dkr.ecr.us-west-2.amazonaws.com --docker-username=AWS --docker-password=$$(aws --region us-west-2 ecr get-login-password)
