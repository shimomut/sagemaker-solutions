
install-kyverno:
	helm repo add kyverno https://kyverno.github.io/kyverno/
	helm repo update
	helm install kyverno kyverno/kyverno --namespace kyverno --create-namespace --version 3.3.6

uninstall-kyverno:
	helm uninstall kyverno -n kyverno

list-kyverno-pods:
	kubectl get pods -n kyverno

apply-permisson:
	kubectl apply -f permission.yaml

edit-config-map:
	kubectl edit configmap kyverno -n kyverno

# remove "system:nodes" from "excludeGroups",
# and remove "[Node,*,*]" from "resourceFilters"

apply-cluster-policy:
	kubectl apply -f cluster-policy.yaml

delete-cluster-policy:
	kubectl delete -f cluster-policy.yaml

list-nodes-with-labels:
	kubectl get nodes -A --show-labels

remove-test-taints:
	kubectl taint nodes --all test-node-taint-123-
