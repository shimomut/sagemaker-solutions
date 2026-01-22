SHELL := /bin/bash

# KubeRay version
KUBERAY_VERSION ?= 1.2.2
NAMESPACE ?= kuberay-system

all:

# Install KubeRay operator using Helm
install-kuberay:
	helm repo add kuberay https://ray-project.github.io/kuberay-helm/
	helm repo update
	helm install kuberay-operator kuberay/kuberay-operator \
		--namespace $(NAMESPACE) \
		--create-namespace \
		--version $(KUBERAY_VERSION)

# Check KubeRay operator status
status:
	kubectl get pods -n $(NAMESPACE)
	kubectl get crd | grep ray

# List Ray clusters
list-clusters:
	kubectl get rayclusters -A

# List Ray services
list-services:
	kubectl get raysvc -A

# List Ray jobs
list-jobs:
	kubectl get rayjobs -A

# Get all Ray resources
list-all:
	kubectl get rayclusters,raysvc,rayjobs -A

# Watch operator logs
watch-logs:
	kubectl logs -f -n $(NAMESPACE) -l app.kubernetes.io/name=kuberay-operator

# Describe operator deployment
describe:
	kubectl describe deployment kuberay-operator -n $(NAMESPACE)

# Upgrade KubeRay operator
upgrade:
	helm repo update
	helm upgrade kuberay-operator kuberay/kuberay-operator \
		--namespace $(NAMESPACE) \
		--version $(KUBERAY_VERSION)

# Uninstall KubeRay operator
uninstall:
	helm uninstall kuberay-operator -n $(NAMESPACE)

# Clean up namespace (use with caution)
clean-namespace:
	kubectl delete namespace $(NAMESPACE)

# Show Helm values
show-values:
	helm show values kuberay/kuberay-operator --version $(KUBERAY_VERSION)

# Get custom values (if you want to customize installation)
get-values:
	helm get values kuberay-operator -n $(NAMESPACE)

.PHONY: all install-kuberay status list-clusters list-services list-jobs list-all \
	watch-logs describe upgrade uninstall clean-namespace show-values get-values
