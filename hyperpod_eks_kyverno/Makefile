
install-kyverno:
	helm repo add kyverno https://kyverno.github.io/kyverno/
	helm repo update
	helm install kyverno kyverno/kyverno --namespace kyverno --create-namespace --version 3.3.6 -f kyverno-values.yaml

uninstall-kyverno:
	helm uninstall kyverno -n kyverno

list-kyverno-pods:
	kubectl get pods -n kyverno

apply-permission:
	kubectl apply -f permission.yaml

delete-permission:
	kubectl delete -f permission.yaml

edit-config-map:
	kubectl edit configmap kyverno -n kyverno

apply-cluster-policy:
	kubectl apply -f cluster-policy.yaml

delete-cluster-policy:
	kubectl delete -f cluster-policy.yaml

list-cluster-policies:
	kubectl get cpol,pol -A

list-nodes-with-labels:
	kubectl get nodes -A --show-labels

remove-test-taints:
	kubectl taint nodes --all test-node-taint-123-
